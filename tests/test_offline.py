"""Offline tests: stubs AstrBot and the RTT API. Run: python -m unittest discover -s tests -t ."""

import asyncio
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))


def _install_astrbot_stub():
    api = types.ModuleType("astrbot.api")
    api.AstrBotConfig = dict
    quiet = lambda *a, **k: None  # noqa: E731
    api.logger = types.SimpleNamespace(warning=quiet, error=quiet, debug=quiet, info=quiet)
    event = types.ModuleType("astrbot.api.event")
    event.AstrMessageEvent = object
    event.filter = types.SimpleNamespace(llm_tool=lambda name=None: (lambda f: f))
    star = types.ModuleType("astrbot.api.star")

    class Star:
        def __init__(self, context):
            self.context = context

    star.Star, star.Context = Star, object
    for n, m in (("astrbot", types.ModuleType("astrbot")), ("astrbot.api", api),
                 ("astrbot.api.event", event), ("astrbot.api.star", star)):
        sys.modules[n] = m


_install_astrbot_stub()
pkg = ROOT.name
main = __import__(f"{pkg}.main", fromlist=["x"])
from importlib import import_module  # noqa: E402

stations = import_module(f"{pkg}.stations")
fmt = import_module(f"{pkg}.formatting")
rtt = import_module(f"{pkg}.rtt_client")


def dep(sched, live=None, late=None, cancelled=False):
    d = {"scheduleAdvertised": sched, "isCancelled": cancelled}
    if live:
        d["realtimeForecast"] = live
        d["realtimeAdvertisedLateness"] = late
    return d


SERVICES = {
    "services": [
        {
            "temporalData": {"departure": dep("2026-11-20T08:10:00Z", "2026-11-20T08:17:00Z", 7), "displayAs": "CALL"},
            "locationMetadata": {"platform": {"planned": "13"}},
            "scheduleMetadata": {"identity": "C11111", "departureDate": "2026-11-20", "modeType": "TRAIN",
                                 "operator": {"code": "VT", "name": "Avanti West Coast"}},
            "destination": [{"location": {"description": "London Euston"}}],
            "reasons": [{"type": "DELAY", "shortText": "Signal failure"}],
        },
        {
            "temporalData": {"departure": dep("2026-11-20T08:40:00Z", cancelled=True), "displayAs": "CANCELLED"},
            "locationMetadata": {"platform": {"planned": "14"}},
            "scheduleMetadata": {"identity": "C22222", "departureDate": "2026-11-20",
                                 "operator": {"name": "Avanti West Coast"}},
            "destination": [{"location": {"description": "London Euston"}}],
        },
        {  # pass-only: must be dropped
            "temporalData": {"pass": {"scheduleAdvertised": "2026-11-20T08:50:00Z"}},
            "scheduleMetadata": {"identity": "X", "departureDate": "2026-11-20"},
        },
    ]
}
SERVICE_DETAIL = {
    "service": {
        "scheduleMetadata": {"identity": "C11111", "departureDate": "2026-11-20", "operator": {"name": "Avanti"}},
        "destination": [{"location": {"description": "London Euston"}}],
        "reasons": [],
        "locations": [
            {"location": {"description": "Manchester Piccadilly", "shortCodes": ["MAN"]},
             "temporalData": {"departure": dep("2026-11-20T08:10:00Z", "2026-11-20T08:17:00Z", 7), "displayAs": "CALL"},
             "locationMetadata": {"platform": {"planned": "13"}}},
            {"location": {"description": "Stockport", "shortCodes": ["SPT"]},
             "temporalData": {"displayAs": "PASS"}},
            {"location": {"description": "London Euston", "shortCodes": ["EUS"]},
             "temporalData": {"arrival": dep("2026-11-20T10:05:00Z", "2026-11-20T10:12:00Z", 7), "displayAs": "CALL"},
             "locationMetadata": {"platform": {"planned": "9"}}},
        ],
    }
}


class FakeClient:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    async def get(self, path, params=None):
        self.calls.append((path, params))
        if self.fail:
            raise self.fail
        if path == "/gb-nr/location":
            return SERVICES
        if path == "/gb-nr/service":
            return SERVICE_DETAIL
        return {"stops": []}

    async def close(self):
        pass


def make(fail=None):
    p = main.UKTrainsPlugin(object(), {"rtt_token": "x", "default_count": 8, "arrival_lookup_count": 4})
    p.client = FakeClient(fail)
    return p


def run(c):
    return asyncio.run(c)


class Tests(unittest.TestCase):
    def test_station_resolution(self):
        r = stations.resolve("Reading")
        self.assertEqual((r.status, r.crs), ("ok", "RDG"))
        self.assertEqual(stations.resolve("paddington").crs, "PAD")
        self.assertEqual(stations.resolve("Manchester Piccadilly").crs, "MAN")
        self.assertEqual(stations.resolve("London Euston").crs, "EUS")
        self.assertEqual(stations.resolve("PAD").crs, "PAD")
        self.assertEqual(stations.resolve("London St Pancras International").crs, "STP")
        self.assertEqual(stations.resolve("London").status, "ambiguous")
        self.assertEqual(stations.resolve("曼彻斯特").status, "ambiguous")
        self.assertEqual(stations.resolve("Manchester").status, "ambiguous")
        self.assertEqual(stations.resolve("Narnia").status, "unknown")
        self.assertEqual(stations.resolve("").status, "unknown")
        # every group member must exist in the table
        for crs in {c for g in stations.GROUPS.values() for c in g}:
            self.assertIn(crs, stations.STATIONS)

    def test_ambiguous_asks_user(self):
        out = run(make().search_trains(None, "Manchester", "London Euston"))
        self.assertIn("Ask the user", out)
        self.assertIn("Manchester Piccadilly (MAN)", out)

    def test_search_ok(self):
        p = make()
        out = run(p.search_trains(None, "Manchester Piccadilly", "London Euston", "2026-11-20", "08:00"))
        print(out)
        self.assertIn("dep 08:10->08:17", out)
        self.assertIn("LATE 7min", out)
        self.assertIn("CANCELLED", out)
        self.assertIn("arr 10:05->10:12", out)
        self.assertIn("plat 13", out)
        self.assertIn("Avanti West Coast", out)
        self.assertNotIn("C22222 | X", out)
        first = p.client.calls[0]
        self.assertEqual(first[1]["code"], "MAN")
        self.assertEqual(first[1]["filterTo"], "EUS")
        self.assertEqual(first[1]["timeFrom"], "2026-11-20T08:00:00")

    def test_detail(self):
        out = run(make().get_train_detail(None, "C11111:2026-11-20"))
        print(out)
        self.assertIn("Manchester Piccadilly", out)
        self.assertNotIn("Stockport", out)
        self.assertIn("London Euston: arr 10:05->10:12", out)

    def test_errors_become_text(self):
        for e in (rtt.RTTError("认证失败"), RuntimeError("boom")):
            out = run(make(fail=e).search_trains(None, "Reading", "Paddington"))
            self.assertIn("failed", out)

    def test_bad_input(self):
        out = run(make().search_trains(None, "Reading", "Paddington", "next blue moon"))
        self.assertIn("Invalid input", out)
        out = run(make().search_trains(None, "Reading", "Reading"))
        self.assertIn("same station", out)

    def test_time_parsing(self):
        self.assertEqual(fmt.parse_time("8am"), "08:00")
        self.assertEqual(fmt.parse_time("0815"), "08:15")
        self.assertEqual(fmt.parse_time("7:05pm"), "19:05")
        self.assertEqual(fmt.split_ref("gb-nr:L01:2026-01-02", None), ("L01", "2026-01-02"))
        # BST/GMT: 2026-07-01T07:00Z is 08:00 in London
        self.assertEqual(fmt.hhmm("2026-07-01T07:00:00Z"), "08:00")
        self.assertEqual(fmt.hhmm("2026-12-01T07:00:00Z"), "07:00")

    def test_no_token(self):
        c = rtt.RTTClient("")
        with self.assertRaises(rtt.RTTError):
            run(c.get("/api/info"))


if __name__ == "__main__":
    unittest.main()
