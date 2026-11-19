"""UK train times for AstrBot: lets the LLM query Realtime Trains via function calling."""

from __future__ import annotations

import asyncio
import time as _time

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

from .formatting import (
    arrival_of,
    find_call,
    parse_date,
    parse_time,
    render_detail,
    render_search,
    split_ref,
)
from .rtt_client import RTTClient, RTTError
from .stations import Resolution, _norm, resolve

_STOPS_TTL = 24 * 3600


class UKTrainsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.client = RTTClient(
            token=config.get("rtt_token", ""),
            timeout=config.get("timeout", 10),
            cache_ttl=config.get("cache_ttl", 60),
        )
        self._stops: dict[str, str] | None = None
        self._stops_ts = 0.0

    async def terminate(self):
        await self.client.close()

    # ------------------------------------------------------------ helpers
    async def _live_stops(self) -> dict[str, str]:
        """Full station list from RTT (/data/stops), used only when the built-in map misses."""
        if self._stops is not None and _time.time() - self._stops_ts < _STOPS_TTL:
            return self._stops
        idx: dict[str, str] = {}
        try:
            data = await self.client.get("/data/stops")
            for s in (data or {}).get("stops", []):
                crs, desc = s.get("shortCode"), s.get("description")
                if crs and desc and s.get("namespace", "gb-nr") == "gb-nr":
                    idx.setdefault(_norm(desc), crs)
                    idx[f"name:{crs}"] = desc
        except RTTError as e:
            logger.warning(f"[uk_trains] could not load live station list: {e}")
        self._stops, self._stops_ts = idx, _time.time()
        return idx

    async def _resolve_station(self, text: str, role: str) -> tuple[Resolution | None, str]:
        """-> (resolution, '') on success, or (None, message-for-the-LLM)."""
        res = resolve(text)
        if res.status == "unknown":
            res = resolve(text, await self._live_stops())
        if res.status == "ok":
            return res, ""
        if res.status == "ambiguous":
            opts = "; ".join(f"{n} ({c})" for c, n in res.candidates)
            return None, (
                f"The {role} '{text}' matches several stations: {opts}. "
                "Do NOT guess. Ask the user which station they mean, then call the tool again."
            )
        return None, (
            f"Could not identify the {role} station '{text}'. "
            "Ask the user for the exact station name (e.g. 'Manchester Piccadilly')."
        )

    # -------------------------------------------------------------- tools
    @filter.llm_tool(name="search_trains")
    async def search_trains(
        self,
        event: AstrMessageEvent,
        origin: str,
        destination: str,
        travel_date: str = "",
        travel_time: str = "",
    ) -> str:
        """Search UK National Rail trains between two stations, with live delays and platforms. Use for questions like next train, trains tomorrow morning, is it delayed. Does NOT provide ticket prices. If the result says a station name is ambiguous, ask the user to choose; never guess.

        Args:
            origin(string): Departure station name or 3-letter CRS code, e.g. Reading, Manchester Piccadilly, PAD
            destination(string): Arrival station name or 3-letter CRS code, e.g. London Paddington, EUS
            travel_date(string): Optional. Date as YYYY-MM-DD, or today/tomorrow. Empty means today (UK time)
            travel_time(string): Optional. Earliest departure time as HH:MM in 24h UK time. Empty means now
        """
        try:
            return await self._search(origin, destination, travel_date, travel_time)
        except RTTError as e:
            return f"Train lookup failed: {e}"
        except Exception as e:  # never let an exception escape into the agent loop
            logger.error(f"[uk_trains] search_trains crashed: {e!r}", exc_info=True)
            return "Train lookup failed because of an internal error. Please try again later."

    @filter.llm_tool(name="get_train_detail")
    async def get_train_detail(
        self,
        event: AstrMessageEvent,
        train_id: str,
        travel_date: str = "",
    ) -> str:
        """Get the full stop list, platforms, live times and delay reasons of one specific UK train. Use the ref value returned by search_trains.

        Args:
            train_id(string): Train reference from search_trains, e.g. L01525:2026-11-20 (or just L01525 with travel_date)
            travel_date(string): Optional. Departure date YYYY-MM-DD if train_id has no date. Empty means today (UK time)
        """
        try:
            ident, dep_date = split_ref(train_id, travel_date)
            d = parse_date(dep_date)
            data = await self.client.get(
                "/gb-nr/service", {"identity": ident, "departureDate": d.isoformat()}
            )
            if not data:
                return "No data found for that train."
            return render_detail(data)
        except ValueError as e:
            return f"Invalid input: {e}"
        except RTTError as e:
            return f"Train lookup failed: {e}"
        except Exception as e:
            logger.error(f"[uk_trains] get_train_detail crashed: {e!r}", exc_info=True)
            return "Train lookup failed because of an internal error. Please try again later."

    # ------------------------------------------------------------- search
    async def _search(self, origin: str, destination: str, d_text: str, t_text: str) -> str:
        o_res, msg = await self._resolve_station(origin, "departure")
        d_res, msg2 = await self._resolve_station(destination, "arrival")
        if not o_res or not d_res:
            return "\n".join(m for m in (msg, msg2) if m)
        if o_res.crs == d_res.crs:
            return "Origin and destination are the same station."

        try:
            day = parse_date(d_text)
            hhmm_ = parse_time(t_text)
        except ValueError as e:
            return f"Invalid input: {e}"

        count = max(1, min(15, int(self.config.get("default_count", 8))))
        window = max(30, min(1439, int(self.config.get("time_window_minutes", 180))))
        params = {
            "code": o_res.crs,
            "filterTo": d_res.crs,
            "timeFrom": f"{day.isoformat()}T{hhmm_}:00",
            "timeWindow": window,
        }
        try:
            data = await self.client.get("/gb-nr/location", params)
        except RTTError as e:
            if e.status != 400:
                raise
            # Some tokens restrict the time-window option: retry with the default window.
            params.pop("timeWindow")
            data = await self.client.get("/gb-nr/location", params)

        when = f"{day.isoformat()} {hhmm_}"
        head = f"{o_res.name} ({o_res.crs}) -> {d_res.name} ({d_res.crs})"
        services = [
            s for s in (data or {}).get("services", [])
            if ((s.get("temporalData") or {}).get("departure") or {}).get("scheduleAdvertised")
            or ((s.get("temporalData") or {}).get("departure") or {}).get("realtimeForecast")
        ]
        if not services:
            return f"{head}: no direct trains found from {when} within {window} min. Try another time, or ask about changing trains."

        services.sort(
            key=lambda s: ((s.get("temporalData") or {}).get("departure") or {}).get("scheduleAdvertised") or ""
        )
        shown = services[:count]

        arrivals = await self._lookup_arrivals(shown, o_res.crs, d_res.crs)
        text = render_search(o_res.name, d_res.name, when, shown, arrivals, len(services))
        if self.config.get("arrival_lookup_count", 4) < len(shown):
            text += "\n(Arrival times only looked up for the first few trains to respect API limits; use get_train_detail for others.)"
        text += "\nNote: no fare/price data available from this source."
        return text

    async def _lookup_arrivals(self, services: list[dict], o_crs: str, d_crs: str) -> dict[str, str]:
        """Arrival time at the destination needs one /service call per train (best effort)."""
        n = max(0, min(10, int(self.config.get("arrival_lookup_count", 4))))
        if n == 0:
            return {}

        async def one(s: dict) -> tuple[str, str]:
            sm = s.get("scheduleMetadata") or {}
            ref = f"{sm.get('identity', '?')}:{sm.get('departureDate', '?')}"
            try:
                data = await self.client.get(
                    "/gb-nr/service",
                    {"identity": sm.get("identity"), "departureDate": sm.get("departureDate")},
                )
                locs = ((data or {}).get("service") or {}).get("locations") or []
                return ref, arrival_of(find_call(locs, d_crs, after_crs=o_crs))
            except Exception as e:  # best effort only
                logger.debug(f"[uk_trains] arrival lookup failed for {ref}: {e}")
                return ref, ""

        results = await asyncio.gather(*(one(s) for s in services[:n] if s.get("scheduleMetadata")))
        return {k: v for k, v in results if v}

