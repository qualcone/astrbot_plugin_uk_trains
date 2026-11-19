"""Pure helpers: time parsing and compact text rendering of RTT responses."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")


def now_london() -> datetime:
    return datetime.now(LONDON)


def parse_date(text: str | None, today: date | None = None) -> date:
    """'' / today / tomorrow / 明天 / YYYY-MM-DD ... -> date. Raises ValueError."""
    today = today or now_london().date()
    t = (text or "").strip().lower()
    if t in ("", "today", "now", "今天", "今日"):
        return today
    if t in ("tomorrow", "明天", "明日"):
        return today + timedelta(days=1)
    if t in ("day after tomorrow", "后天"):
        return today + timedelta(days=2)
    if t in ("yesterday", "昨天"):
        return today - timedelta(days=1)
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    raise ValueError(f"无法识别日期 '{text}'，请使用 YYYY-MM-DD。")


def parse_time(text: str | None, now: datetime | None = None) -> str:
    """'' / now / HH:MM / HHMM / 8am -> 'HH:MM'. Raises ValueError."""
    t = (text or "").strip().lower()
    if t in ("", "now", "现在"):
        return (now or now_london()).strftime("%H:%M")
    m = re.fullmatch(r"(\d{1,2})(?::?(\d{2}))?\s*(am|pm)?", t)
    if not m:
        raise ValueError(f"无法识别时间 '{text}'，请使用 HH:MM（24 小时制）。")
    h, mi, ap = int(m[1]), int(m[2] or 0), m[3]
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        raise ValueError(f"时间 '{text}' 不合法。")
    return f"{h:02d}:{mi:02d}"


def _dt(s: Any) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=LONDON)
    return d.astimezone(LONDON)


def hhmm(s: Any) -> str:
    d = _dt(s)
    return d.strftime("%H:%M") if d else "--"


def _platform(meta: dict | None) -> str:
    p = ((meta or {}).get("platform") or {})
    return str(p.get("actual") or p.get("planned") or "") or "?"


def best_time(t: dict | None) -> tuple[str, str]:
    """-> (scheduled HH:MM, expected/actual HH:MM or '')."""
    t = t or {}
    sched = hhmm(t.get("scheduleAdvertised") or t.get("scheduleInternal"))
    live = t.get("realtimeActual") or t.get("realtimeForecast") or t.get("realtimeEstimate")
    return sched, (hhmm(live) if live else "")


def status_of(temporal: dict, key: str = "departure") -> str:
    """Compact status: Cancelled / On time / Late 5m / No report / Scheduled."""
    leg = temporal.get(key) or {}
    if leg.get("isCancelled") or temporal.get("displayAs") == "CANCELLED":
        return "CANCELLED"
    late = leg.get("realtimeAdvertisedLateness")
    if late is None:
        late = leg.get("realtimeInternalLateness")
    has_live = leg.get("realtimeActual") or leg.get("realtimeForecast")
    if has_live and isinstance(late, int):
        if late >= 1:
            return f"LATE {late}min"
        return "on time" if late == 0 else f"early {-late}min"
    if leg.get("realtimeNoReport"):
        return "no report"
    return "scheduled"


def reason_text(reasons: Any, limit: int = 1) -> str:
    out = []
    for r in reasons or []:
        txt = r.get("longText") or r.get("shortText")
        if txt:
            out.append(txt)
        if len(out) >= limit:
            break
    return "; ".join(out)


def dest_name(svc: dict) -> str:
    d = svc.get("destination") or []
    names = [((x or {}).get("location") or {}).get("description") for x in d]
    return " / ".join(n for n in names if n) or "?"


def service_ref(svc: dict) -> str:
    sm = svc.get("scheduleMetadata") or {}
    return f"{sm.get('identity', '?')}:{sm.get('departureDate', '?')}"


def split_ref(train_id: str, dep_date: str | None) -> tuple[str, str | None]:
    """Accept 'L01525', 'L01525:2025-10-26' or 'gb-nr:L01525:2025-10-26'."""
    t = (train_id or "").strip()
    if t.lower().startswith("gb-nr:"):
        t = t[6:]
    m = re.fullmatch(r"(.+):(\d{4}-\d{2}-\d{2})", t)
    if m:
        return m[1], m[2]
    return t, (dep_date or None)


def find_call(locations: list[dict], crs: str, after_crs: str | None = None) -> dict | None:
    """Locate the stop for `crs`, preferring one after `after_crs` in the calling order."""
    start = 0
    if after_crs:
        for i, loc in enumerate(locations):
            if after_crs in ((loc.get("location") or {}).get("shortCodes") or []):
                start = i + 1
                break
    for loc in locations[start:]:
        if crs in ((loc.get("location") or {}).get("shortCodes") or []):
            return loc
    return None


def arrival_of(loc: dict | None) -> str:
    if not loc:
        return ""
    td = loc.get("temporalData") or {}
    arr = td.get("arrival") or {}
    if arr.get("isCancelled") or td.get("displayAs") == "CANCELLED":
        return "cancelled"
    sched, live = best_time(arr)
    if sched == "--" and not live:
        return ""
    return f"{sched}->{live}" if live and live != sched else sched


def render_search(
    origin: str,
    dest: str,
    when: str,
    services: list[dict],
    arrivals: dict[str, str],
    total_found: int,
) -> str:
    lines = [f"{origin} -> {dest}, from {when} (UK time). Showing {len(services)} of {total_found}."]
    for i, s in enumerate(services, 1):
        td = s.get("temporalData") or {}
        sm = s.get("scheduleMetadata") or {}
        dep = td.get("departure") or {}
        sched, live = best_time(dep)
        dep_txt = f"{sched}->{live}" if live and live != sched else sched
        st = status_of(td)
        extra = []
        arr = arrivals.get(service_ref(s))
        if arr:
            extra.append(f"arr {arr}")
        extra.append(f"plat {_platform(s.get('locationMetadata'))}")
        op = (sm.get("operator") or {}).get("name") or (sm.get("operator") or {}).get("code")
        if op:
            extra.append(str(op))
        if sm.get("modeType") and sm["modeType"] != "TRAIN":
            extra.append(str(sm["modeType"]).replace("_", " ").lower())
        why = reason_text(s.get("reasons"))
        line = f"{i}. dep {dep_txt} | {st} | " + " | ".join(extra) + f" | to {dest_name(s)} | ref {service_ref(s)}"
        if why and st not in ("on time", "scheduled"):
            line += f" | reason: {why}"
        lines.append(line)
    return "\n".join(lines)


def render_detail(data: dict) -> str:
    svc = data.get("service") or {}
    sm = svc.get("scheduleMetadata") or {}
    locs = svc.get("locations") or []
    op = (sm.get("operator") or {}).get("name", "?")
    head = (
        f"Train {sm.get('identity', '?')} on {sm.get('departureDate', '?')} | {op} | "
        f"to {dest_name(svc)}"
    )
    why = reason_text(svc.get("reasons"), limit=2)
    lines = [head]
    if why:
        lines.append(f"Reason: {why}")
    for loc in locs:
        td = loc.get("temporalData") or {}
        disp = td.get("displayAs")
        if disp in (None, "PASS"):  # skip pass-through points to stay short
            continue
        name = (loc.get("location") or {}).get("description", "?")
        arr = td.get("arrival") or {}
        dep = td.get("departure") or {}
        a_s, a_l = best_time(arr) if arr else ("", "")
        d_s, d_l = best_time(dep) if dep else ("", "")
        parts = []
        if a_s and a_s != "--":
            parts.append(f"arr {a_s}" + (f"->{a_l}" if a_l and a_l != a_s else ""))
        if d_s and d_s != "--":
            parts.append(f"dep {d_s}" + (f"->{d_l}" if d_l and d_l != d_s else ""))
        leg = "arrival" if arr and not dep else "departure"
        st = status_of(td, leg)
        plat = _platform(loc.get("locationMetadata"))
        lines.append(
            f"- {name}: {' '.join(parts) or '-'} | plat {plat} | {st if disp != 'CANCELLED' else 'CANCELLED'}"
        )
    return "\n".join(lines)
