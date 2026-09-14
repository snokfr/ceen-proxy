"""Small formatting helpers shared by the brain and the window.

Anything that turns raw values into human-friendly text lives here, so
both the engine and every screen format things the same way.
"""

from __future__ import annotations

from typing import Dict, Optional

# ── byte counts ──────────────────────────────────────────────────────────────

def fmt_bytes(n: float) -> str:
    """1234567 -> '1.2 MB'. Walks up the units until the number is small."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ── countries ────────────────────────────────────────────────────────────────

# ISO code -> English name for the codes free proxy lists actually emit.
COUNTRY_NAMES: Dict[str, str] = {
    "US": "United States", "GB": "United Kingdom", "DE": "Germany",
    "FR": "France", "NL": "Netherlands", "CA": "Canada", "RU": "Russia",
    "CN": "China", "BR": "Brazil", "IN": "India", "JP": "Japan",
    "AU": "Australia", "ID": "Indonesia", "VN": "Vietnam",
    "TH": "Thailand", "PH": "Philippines", "UA": "Ukraine", "PL": "Poland",
    "ES": "Spain", "IT": "Italy", "SE": "Sweden", "CH": "Switzerland",
    "RO": "Romania", "BG": "Bulgaria", "MX": "Mexico", "AR": "Argentina",
    "KR": "South Korea", "SG": "Singapore", "HK": "Hong Kong", "TW": "Taiwan",
    "TR": "Turkey", "IR": "Iran", "PK": "Pakistan", "BD": "Bangladesh",
    "EG": "Egypt", "ZA": "South Africa", "NG": "Nigeria", "KE": "Kenya",
    "CO": "Colombia", "CL": "Chile", "PE": "Peru", "EC": "Ecuador",
    "MY": "Malaysia", "KZ": "Kazakhstan", "CZ": "Czechia", "AT": "Austria",
    "BE": "Belgium", "DK": "Denmark", "NO": "Norway", "FI": "Finland",
    "PT": "Portugal", "GR": "Greece", "HU": "Hungary", "IL": "Israel",
    "AE": "UAE", "IQ": "Iraq", "SC": "Seychelles", "PA": "Panama",
}

_FLAG_CACHE: Dict[str, str] = {}


def country_name(cc: Optional[str], fallback: Optional[str] = None) -> str:
    """Best human name for a country code like 'US'."""
    if cc and cc.upper() in COUNTRY_NAMES:
        return COUNTRY_NAMES[cc.upper()]
    return fallback or cc or "Unknown"


def flag_emoji(cc: Optional[str]) -> str:
    """Two-letter country badge text, e.g. 'US'.

    Used to be a flag EMOJI, but UI fonts on Windows often render those
    as '?'. A colored two-letter badge looks just as clean and ALWAYS
    renders (the blue chip style is applied by the UI layer).
    """
    if not cc or len(cc) != 2 or not cc.isalpha():
        return "--"
    cc = cc.upper()
    _FLAG_CACHE[cc] = cc
    return cc


# ── latency ──────────────────────────────────────────────────────────────────

# (r, g, b) colors per quality band — kept here so core + ui agree.
_LATENCY_COLORS = {
    "great": (46, 204, 113),
    "good": (66, 133, 244),
    "slow": (255, 168, 46),
    "very slow": (235, 77, 61),
    "n/a": (90, 96, 108),
}


def latency_color(ms: Optional[int]):
    """Pick the color for a ping value (great=green … very slow=red)."""
    return _LATENCY_COLORS[latency_word(ms)]


def latency_word(ms: Optional[int]) -> str:
    """A one-word quality label for a ping, for accessibility/log lines."""
    if ms is None:
        return "n/a"
    if ms < 300:
        return "great"
    if ms < 900:
        return "good"
    if ms < 2200:
        return "slow"
    return "very slow"
