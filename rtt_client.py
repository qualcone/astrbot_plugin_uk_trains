"""Thin async client for the Realtime Trains next-generation API (https://data.rtt.io).

The old api.rtt.io (HTTP Basic) is shut down. The new API uses a Bearer token, which is
either a long-life access token or a refresh token (exchanged via /api/get_access_token).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp

BASE_URL = "https://data.rtt.io"


class RTTError(Exception):
    """Error whose message is safe to show to the end user."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class RTTClient:
    def __init__(self, token: str, timeout: float = 10.0, cache_ttl: float = 60.0):
        self.token = (token or "").strip()
        self.timeout = max(3.0, float(timeout))
        self.cache_ttl = max(0.0, float(cache_ttl))
        self._cache: dict[tuple, tuple[float, Any]] = {}
        self._inflight: dict[tuple, asyncio.Future] = {}
        self._access_token: str | None = None
        self._access_expiry: float = 0.0
        self._session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    # ---------------------------------------------------------------- auth
    async def _exchange_refresh_token(self) -> str:
        """Try to treat the configured token as a refresh token."""
        session = self._get_session()
        async with session.get(
            f"{BASE_URL}/api/get_access_token",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        ) as r:
            if r.status != 200:
                raise RTTError(
                    "RTT 拒绝了该 Token（认证失败）。请到 https://api-portal.rtt.io 检查或重新生成 Token。"
                )
            data = await r.json(content_type=None)
        tok = data.get("token")
        if not tok:
            raise RTTError("RTT 认证返回异常，未取得 access token。")
        self._access_token = tok
        try:
            until = datetime.fromisoformat(str(data.get("validUntil")).replace("Z", "+00:00"))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            self._access_expiry = time.time() + max(
                0.0, (until - datetime.now(timezone.utc)).total_seconds() - 30
            )
        except Exception:
            self._access_expiry = time.time() + 300
        return tok

    def _current_bearer(self) -> str:
        if self._access_token and time.time() < self._access_expiry:
            return self._access_token
        return self.token

    # ------------------------------------------------------------- request
    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET with short-lived cache and in-flight de-duplication.

        Returns parsed JSON, or None for HTTP 204 (valid query, nothing found).
        Raises RTTError with a user-presentable message on any failure.
        """
        if not self.token:
            raise RTTError(
                "尚未配置 RTT Token。请管理员在插件配置中填写（注册地址：https://api-portal.rtt.io）。"
            )
        key = (path, tuple(sorted((params or {}).items())))
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < self.cache_ttl:
            return hit[1]
        if key in self._inflight:  # identical request already running -> share it
            return await asyncio.shield(self._inflight[key])

        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            result = await self._fetch(path, params)
            self._cache[key] = (time.time(), result)
            if len(self._cache) > 300:  # cheap bound on memory
                for k in sorted(self._cache, key=lambda k: self._cache[k][0])[:100]:
                    self._cache.pop(k, None)
            fut.set_result(result)
            return result
        except BaseException as e:
            fut.set_exception(e)
            fut.exception()  # mark retrieved so asyncio doesn't warn
            raise
        finally:
            self._inflight.pop(key, None)

    async def _fetch(self, path: str, params: dict[str, Any] | None, _retried: bool = False) -> Any:
        session = self._get_session()
        headers = {"Authorization": f"Bearer {self._current_bearer()}", "Accept": "application/json"}
        try:
            async with session.get(f"{BASE_URL}{path}", params=params, headers=headers) as r:
                status = r.status
                if status == 204:
                    return None
                if status == 200:
                    return await r.json(content_type=None)
                retry_after = r.headers.get("Retry-After", "")
                body = (await r.text())[:200]
        except asyncio.TimeoutError:
            raise RTTError("请求 RTT 超时，请稍后再试。") from None
        except aiohttp.ClientError as e:
            raise RTTError(f"无法连接 RTT 服务（网络错误：{type(e).__name__}）。") from None

        if status in (401, 403):
            if not _retried and self._access_token is None:
                # The token may be a refresh token: exchange it once and retry.
                try:
                    await self._exchange_refresh_token()
                except asyncio.TimeoutError:
                    raise RTTError("请求 RTT 超时，请稍后再试。") from None
                except aiohttp.ClientError as e:
                    raise RTTError(f"无法连接 RTT 服务（网络错误：{type(e).__name__}）。") from None
                return await self._fetch(path, params, _retried=True)
            raise RTTError(
                "RTT 认证失败或无权访问该数据（401/403）。请检查插件配置的 Token 是否正确、是否过期。"
            )
        if status == 429:
            wait = f"，约 {retry_after} 秒后可重试" if retry_after.isdigit() else ""
            raise RTTError(f"RTT 接口达到频率限制{wait}。请稍后再问。")
        if status == 404:
            raise RTTError("RTT 没有找到对应的列车/车站数据（404）。")
        if status == 400:
            raise RTTError(f"RTT 认为查询参数无效（400）：{body}", status=400)
        if status >= 500:
            raise RTTError(f"RTT 服务暂时不可用（{status}），请稍后再试。")
        raise RTTError(f"RTT 返回了意外状态 {status}。")
