"""In-memory display names, GICS styles and US issuer identities."""

import re

from us_watchlist.domain.iwb_company_names import COMPANIES

STYLES = ("防御", "成长", "周期")
SECTORS = {
    "Utilities": ("公用事业", "防御"),
    "Health Care": ("医疗保健", "防御"),
    "Consumer Staples": ("日常消费", "防御"),
    "Real Estate": ("房地产/REITs", "防御"),
    "Information Technology": ("信息技术", "成长"),
    "Communication": ("通信服务", "成长"),
    "Consumer Discretionary": ("可选消费", "成长"),
    "Industrials": ("工业", "周期"),
    "Financials": ("金融", "周期"),
    "Materials": ("原材料", "周期"),
    "Energy": ("能源", "周期"),
}
_UNKNOWN = ("未标注板块", "未分类")
_ISSUERS = {
    "ALPHABET": ("GOOGL", "GOOG"),
    "LIBERTY LIVE": ("LLYVA", "LLYVK", "LLYVB"),
    "LIBERTY MEDIA": ("FWONA", "FWONK", "FWONB"),
    "FOX": ("FOX", "FOXA"),
    "NEWS": ("NWS", "NWSA"),
    "BROWN FORMAN": ("BF-A", "BF-B"),
    "BERKSHIRE HATHAWAY": ("BRK-A", "BRK-B"),
    "LENNAR": ("LEN", "LEN-B"),
    "U HAUL": ("UHAL", "UHAL-B"),
    "HEICO": ("HEI", "HEI-A"),
    "ZILLOW GROUP": ("Z", "ZG"),
    "LIBERTY GLOBAL": ("LBTYA", "LBTYB", "LBTYK"),
}
_ISSUER_BY_SYMBOL = {symbol: issuer for issuer, symbols in _ISSUERS.items() for symbol in symbols}
_SUFFIX = re.compile(
    r"(?:[ ,]+(?:CLASS [ABCK]|SERIES [ABCK]|INC(?:ORPORATED)?|CORP(?:ORATION)?|PLC|LTD|LLC)\.?)+$",
    re.IGNORECASE,
)


def _clean_name(english_name: str) -> str:
    return _SUFFIX.sub("", " ".join(english_name.split())).strip(" ,")


def company_name(symbol: str, english_name: str = "") -> str:
    company = COMPANIES.get(symbol.upper().replace(".", "-"))
    return company[0] if company else _clean_name(english_name) or symbol


def sector_style(sector: str) -> tuple[str, str]:
    normalized = " ".join(sector.split())
    return SECTORS.get("Communication" if normalized == "Communication Services" else normalized, _UNKNOWN)


def catalog_sector_style(symbol: str) -> tuple[str, str]:
    company = COMPANIES.get(symbol.upper().replace(".", "-"))
    return sector_style(company[1]) if company else _UNKNOWN


def issuer_key(symbol: str, english_name: str = "") -> str:
    ticker = symbol.upper().replace(".", "-")
    explicit = _ISSUER_BY_SYMBOL.get(ticker)
    if explicit is not None:
        return explicit
    normalized = " ".join(re.findall(r"[A-Z0-9]+", _clean_name(english_name).upper()))
    return normalized or f"TICKER:{ticker}"
