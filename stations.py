"""Station-name -> CRS code resolution.

STATIONS: crs -> (display name, extra aliases)
GROUPS:   city/area name -> list of CRS codes (ambiguous, must be confirmed by the user)
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# crs: (official name, (aliases...))  aliases are matched after normalisation
STATIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    # ---- London ----
    "KGX": ("London King's Cross", ("kings cross", "king cross", "国王十字", "国王十字站")),
    "EUS": ("London Euston", ("euston", "尤斯顿", "尤斯顿站")),
    "PAD": ("London Paddington", ("paddington", "帕丁顿", "帕丁顿站")),
    "STP": ("London St Pancras International", ("st pancras", "saint pancras", "st pancras international", "圣潘克拉斯")),
    "VIC": ("London Victoria", ("victoria", "维多利亚", "维多利亚站")),
    "WAT": ("London Waterloo", ("waterloo", "滑铁卢", "滑铁卢站")),
    "WAE": ("London Waterloo East", ("waterloo east",)),
    "LST": ("London Liverpool Street", ("liverpool street", "liverpool st", "利物浦街")),
    "LBG": ("London Bridge", ("london bridge", "伦敦桥")),
    "CHX": ("London Charing Cross", ("charing cross", "查令十字")),
    "MYB": ("London Marylebone", ("marylebone", "马里波恩")),
    "FST": ("London Fenchurch Street", ("fenchurch street", "芬丘奇街")),
    "CST": ("London Cannon Street", ("cannon street", "坎农街")),
    "BFR": ("London Blackfriars", ("blackfriars",)),
    "MOG": ("London Moorgate", ("moorgate",)),
    "ZFD": ("London Farringdon", ("farringdon",)),
    "CTK": ("London City Thameslink", ("city thameslink",)),
    "CLJ": ("Clapham Junction", ("clapham junction", "克拉彭枢纽")),
    "SRA": ("London Stratford", ("stratford", "stratford london", "斯特拉特福")),
    "WIM": ("Wimbledon", ("温布尔登",)),
    "RMD": ("Richmond (London)", ("richmond",)),
    "ECR": ("East Croydon", ("croydon east",)),
    "WCY": ("West Croydon", ("croydon west",)),
    # ---- London airports ----
    "GTW": ("Gatwick Airport", ("gatwick", "盖特威克", "盖特威克机场")),
    "HXX": ("Heathrow Terminals 2 & 3", ("heathrow", "heathrow t2", "heathrow t3", "heathrow terminal 2", "heathrow terminal 3", "希思罗", "希思罗机场")),
    "HAF": ("Heathrow Terminal 4", ("heathrow t4", "heathrow terminal 4")),
    "HWV": ("Heathrow Terminal 5", ("heathrow t5", "heathrow terminal 5")),
    "SSD": ("London Stansted Airport", ("stansted", "stansted airport", "斯坦斯特德")),
    "LTN": ("Luton Airport Parkway", ("luton airport", "luton parkway", "卢顿机场")),
    # ---- North West ----
    "MAN": ("Manchester Piccadilly", ("manchester piccadilly", "piccadilly", "曼彻斯特皮卡迪利", "皮卡迪利")),
    "MCV": ("Manchester Victoria", ("manchester victoria", "曼彻斯特维多利亚")),
    "MCO": ("Manchester Oxford Road", ("manchester oxford road", "oxford road", "牛津路")),
    "DGT": ("Deansgate", ("manchester deansgate", "迪恩斯盖特")),
    "MIA": ("Manchester Airport", ("曼彻斯特机场",)),
    "LIV": ("Liverpool Lime Street", ("lime street", "liverpool lime street", "利物浦莱姆街")),
    "LVC": ("Liverpool Central", ("liverpool central",)),
    "PRE": ("Preston", ("普雷斯顿",)),
    "LAN": ("Lancaster", ("兰开斯特",)),
    "CAR": ("Carlisle", ("卡莱尔",)),
    "CRE": ("Crewe", ("克鲁",)),
    "CTR": ("Chester", ("切斯特",)),
    "WGN": ("Wigan North Western", ("wigan",)),
    "WGW": ("Wigan Wallgate", ()),
    "BON": ("Bolton", ("博尔顿",)),
    "BPN": ("Blackpool North", ("blackpool", "布莱克浦")),
    "SPT": ("Stockport", ("斯托克波特",)),
    "WBQ": ("Warrington Bank Quay", ("warrington", "bank quay")),
    "WAC": ("Warrington Central", ()),
    # ---- Yorkshire / North East ----
    "LDS": ("Leeds", ("利兹",)),
    "SHF": ("Sheffield", ("谢菲尔德",)),
    "YRK": ("York", ("约克",)),
    "NCL": ("Newcastle", ("newcastle upon tyne", "纽卡斯尔")),
    "DON": ("Doncaster", ("唐卡斯特",)),
    "HUL": ("Hull", ("kingston upon hull", "赫尔")),
    "HGT": ("Harrogate", ("哈罗盖特",)),
    "DHM": ("Durham", ("达勒姆", "杜伦")),
    "DAR": ("Darlington", ("达灵顿",)),
    "MBR": ("Middlesbrough", ("米德尔斯堡",)),
    "SUN": ("Sunderland", ("桑德兰",)),
    "WKF": ("Wakefield Westgate", ("wakefield",)),
    "WKK": ("Wakefield Kirkgate", ()),
    "HUD": ("Huddersfield", ("哈德斯菲尔德",)),
    "BDI": ("Bradford Interchange", ("bradford", "布拉德福德")),
    "BDQ": ("Bradford Forster Square", ("forster square",)),
    "HFX": ("Halifax", ("哈利法克斯",)),
    # ---- Midlands ----
    "BHM": ("Birmingham New Street", ("new street", "birmingham new street", "伯明翰新街")),
    "BMO": ("Birmingham Moor Street", ("moor street", "birmingham moor street")),
    "BSW": ("Birmingham Snow Hill", ("snow hill", "birmingham snow hill")),
    "BHI": ("Birmingham International", ("birmingham airport", "伯明翰机场")),
    "NOT": ("Nottingham", ("诺丁汉",)),
    "LEC": ("Leicester", ("莱斯特",)),
    "DBY": ("Derby", ("德比",)),
    "SOT": ("Stoke-on-Trent", ("stoke", "斯托克")),
    "COV": ("Coventry", ("考文垂",)),
    "WVH": ("Wolverhampton", ("伍尔弗汉普顿",)),
    "SHR": ("Shrewsbury", ("什鲁斯伯里",)),
    "LNC": ("Lincoln", ("lincoln central", "林肯")),
    "GRA": ("Grantham", ()),
    "NNG": ("Newark North Gate", ("newark",)),
    "RUG": ("Rugby", ("拉格比",)),
    "NMP": ("Northampton", ("北安普顿",)),
    "TAM": ("Tamworth", ()),
    "MKC": ("Milton Keynes Central", ("milton keynes", "mk", "米尔顿凯恩斯")),
    "WOF": ("Worcester Foregate Street", ("worcester foregate street", "foregate street")),
    "WOS": ("Worcester Shrub Hill", ("shrub hill",)),
    "HFD": ("Hereford", ("赫里福德",)),
    # ---- East ----
    "CBG": ("Cambridge", ("剑桥",)),
    "PBO": ("Peterborough", ("彼得伯勒",)),
    "NRW": ("Norwich", ("诺里奇",)),
    "IPS": ("Ipswich", ("伊普斯威奇",)),
    "COL": ("Colchester", ("科尔切斯特",)),
    "CHM": ("Chelmsford", ("切姆斯福德",)),
    "SOV": ("Southend Victoria", ("southend", "southend-on-sea")),
    "SOC": ("Southend Central", ()),
    "ELY": ("Ely", ()),
    "BDM": ("Bedford", ("贝德福德",)),
    "SVG": ("Stevenage", ("斯蒂芬尼奇",)),
    "WFJ": ("Watford Junction", ("watford", "沃特福德")),
    "LUT": ("Luton", ("卢顿",)),
    # ---- South / South East ----
    "RDG": ("Reading", ("雷丁",)),
    "OXF": ("Oxford", ("牛津",)),
    "BTN": ("Brighton", ("布莱顿", "布赖顿")),
    "SOU": ("Southampton Central", ("southampton", "南安普顿")),
    "SOA": ("Southampton Airport Parkway", ("southampton airport",)),
    "PMS": ("Portsmouth & Southsea", ("portsmouth", "portsmouth and southsea", "朴茨茅斯")),
    "PMH": ("Portsmouth Harbour", ()),
    "WIN": ("Winchester", ("温彻斯特",)),
    "GLD": ("Guildford", ("吉尔福德",)),
    "WOK": ("Woking", ("沃金",)),
    "BSK": ("Basingstoke", ("贝辛斯托克",)),
    "SLO": ("Slough", ("斯劳",)),
    "MAI": ("Maidenhead", ("梅登黑德",)),
    "DID": ("Didcot Parkway", ("didcot",)),
    "SAL": ("Salisbury", ("索尔兹伯里",)),
    "CBW": ("Canterbury West", ("canterbury", "坎特伯雷")),
    "CBE": ("Canterbury East", ()),
    "DVP": ("Dover Priory", ("dover", "多佛")),
    "AFK": ("Ashford International", ("ashford", "ashford kent")),
    "BMH": ("Bournemouth", ("伯恩茅斯",)),
    "POO": ("Poole", ()),
    "WEY": ("Weymouth", ()),
    # ---- South West / Wales ----
    "BRI": ("Bristol Temple Meads", ("temple meads", "bristol temple meads", "布里斯托尔")),
    "BPW": ("Bristol Parkway", ()),
    "BTH": ("Bath Spa", ("bath", "巴斯")),
    "EXD": ("Exeter St Davids", ("exeter", "exeter st davids", "埃克塞特")),
    "EXC": ("Exeter Central", ()),
    "PLY": ("Plymouth", ("普利茅斯",)),
    "TAU": ("Taunton", ()),
    "TRU": ("Truro", ()),
    "PNZ": ("Penzance", ("彭赞斯",)),
    "SWI": ("Swindon", ("斯温登",)),
    "GCR": ("Gloucester", ("格洛斯特",)),
    "CNM": ("Cheltenham Spa", ("cheltenham", "切尔滕纳姆")),
    "CDF": ("Cardiff Central", ("cardiff", "卡迪夫")),
    "CDQ": ("Cardiff Queen Street", ()),
    "NWP": ("Newport (South Wales)", ("newport", "纽波特")),
    "SWA": ("Swansea", ("斯旺西",)),
    "WXM": ("Wrexham General", ("wrexham",)),
    "HHD": ("Holyhead", ()),
    "BNG": ("Bangor (Gwynedd)", ("bangor",)),
    "AYW": ("Aberystwyth", ()),
    # ---- Scotland ----
    "EDB": ("Edinburgh Waverley", ("edinburgh", "waverley", "爱丁堡")),
    "HYM": ("Edinburgh Haymarket", ("haymarket",)),
    "GLC": ("Glasgow Central", ("glasgow central", "格拉斯哥中央")),
    "GLQ": ("Glasgow Queen Street", ("queen street glasgow",)),
    "ABD": ("Aberdeen", ("阿伯丁",)),
    "INV": ("Inverness", ("因弗内斯",)),
    "DEE": ("Dundee", ("邓迪",)),
    "PTH": ("Perth", ()),
    "STG": ("Stirling", ("斯特灵",)),
    "FTW": ("Fort William", ()),
    "OBN": ("Oban", ()),
}

# Ambiguous names -> candidate CRS codes. The tool must never pick one silently.
GROUPS: dict[str, tuple[str, ...]] = {
    "london": ("KGX", "EUS", "PAD", "STP", "VIC", "WAT", "LST", "LBG", "CHX", "MYB", "FST", "CST", "BFR", "MOG", "SRA", "CLJ"),
    "伦敦": ("KGX", "EUS", "PAD", "STP", "VIC", "WAT", "LST", "LBG", "CHX", "MYB", "FST", "CST", "BFR", "MOG", "SRA", "CLJ"),
    "manchester": ("MAN", "MCV", "MCO", "DGT"),
    "曼彻斯特": ("MAN", "MCV", "MCO", "DGT"),
    "birmingham": ("BHM", "BMO", "BSW", "BHI"),
    "伯明翰": ("BHM", "BMO", "BSW", "BHI"),
    "glasgow": ("GLC", "GLQ"),
    "格拉斯哥": ("GLC", "GLQ"),
    "liverpool": ("LIV", "LVC"),
    "利物浦": ("LIV", "LVC"),
    "bristol": ("BRI", "BPW"),
    "worcester": ("WOF", "WOS"),
    "wakefield": ("WKF", "WKK"),
    "bradford": ("BDI", "BDQ"),
    "wigan": ("WGN", "WGW"),
    "warrington": ("WBQ", "WAC"),
    "southend": ("SOV", "SOC"),
    "portsmouth": ("PMS", "PMH"),
    "southampton": ("SOU", "SOA"),
    "cardiff": ("CDF", "CDQ"),
    "canterbury": ("CBW", "CBE"),
    "exeter": ("EXD", "EXC"),
    "croydon": ("ECR", "WCY"),
    "heathrow": ("HXX", "HAF", "HWV"),
    "希思罗": ("HXX", "HAF", "HWV"),
    "edinburgh": ("EDB", "HYM"),
    "luton": ("LUT", "LTN"),
}
# Group names that, when typed exactly, should be treated as ambiguous even if an
# individual alias also exists (these override the alias table).
_GROUP_OVERRIDES = set(GROUPS)


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = s.replace("’", "'").replace("‘", "'")
    s = re.sub(r"\b(railway|rail|train)?\s*station\b", " ", s)
    s = re.sub(r"[站車车]$", "", s)
    s = re.sub(r"[^a-z0-9一-鿿& ]", "", s.replace("'", ""))
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Resolution:
    """Result of resolving a user-supplied station string."""

    status: str  # "ok" | "ambiguous" | "unknown"
    crs: str = ""
    name: str = ""
    candidates: list[tuple[str, str]] = field(default_factory=list)  # (crs, name)


def _build_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for crs, (name, aliases) in STATIONS.items():
        idx[_norm(name)] = crs
        for a in aliases:
            idx.setdefault(_norm(a), crs)
        # "London King's Cross" -> also index without the "london " prefix
        n = _norm(name)
        if n.startswith("london "):
            idx.setdefault(n[len("london "):], crs)
    return idx


_INDEX = _build_index()


def station_name(crs: str) -> str:
    return STATIONS.get(crs.upper(), (crs.upper(), ()))[0]


def resolve(query: str, extra: dict[str, str] | None = None) -> Resolution:
    """Resolve free text to one CRS code, an ambiguity list, or unknown.

    `extra` is an optional {normalised name: crs} map (e.g. the live /data/stops list)
    consulted only when the built-in table has no answer.
    """
    q = _norm(query or "")
    if not q:
        return Resolution("unknown")

    # 1. Ambiguous city/area names win over single-station aliases.
    if q in _GROUP_OVERRIDES:
        cands = [(c, station_name(c)) for c in GROUPS[q]]
        return Resolution("ambiguous", candidates=cands)

    # 2. Exact name / alias.
    if q in _INDEX:
        crs = _INDEX[q]
        return Resolution("ok", crs=crs, name=station_name(crs))

    # 3. Three-letter CRS typed directly (e.g. "PAD", "RDG").
    if re.fullmatch(r"[a-z]{3}", q):
        crs = q.upper()
        if crs in STATIONS:
            return Resolution("ok", crs=crs, name=station_name(crs))

    # 4. Live station list (optional).
    if extra:
        if q in extra:
            crs = extra[q]
            return Resolution("ok", crs=crs, name=extra.get(f"name:{crs}", crs))
        hits = [(c, extra.get(f"name:{c}", c)) for n, c in extra.items()
                if not n.startswith("name:") and q in n]
        hits = list(dict.fromkeys(hits))
        if len(hits) == 1:
            return Resolution("ok", crs=hits[0][0], name=hits[0][1])
        if 1 < len(hits) <= 8:
            return Resolution("ambiguous", candidates=hits)

    # 5. Substring / fuzzy match on built-in names.
    sub = list(dict.fromkeys(c for n, c in _INDEX.items() if len(q) >= 4 and q in n))
    if len(sub) == 1:
        return Resolution("ok", crs=sub[0], name=station_name(sub[0]))
    if 1 < len(sub) <= 8:
        return Resolution("ambiguous", candidates=[(c, station_name(c)) for c in sub])

    close = difflib.get_close_matches(q, list(_INDEX), n=3, cutoff=0.8)
    cands = list(dict.fromkeys(_INDEX[c] for c in close))
    if len(cands) == 1:
        # A single near-miss is still a guess -> ask the user rather than assume.
        return Resolution("ambiguous", candidates=[(cands[0], station_name(cands[0]))])
    if cands:
        return Resolution("ambiguous", candidates=[(c, station_name(c)) for c in cands])
    return Resolution("unknown")
