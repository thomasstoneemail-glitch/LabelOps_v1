"""Address parsing and normalization for messy Telegram-pasted UK addresses."""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Iterable, List, Dict


UK_COUNTRY_VARIANTS = {
    "UK",
    "U.K",
    "U.K.",
    "UNITED KINGDOM",
    "GREAT BRITAIN",
    "GB",
    "BRITAIN",
    "ENGLAND",
    "SCOTLAND",
    "WALES",
    "NORTHERN IRELAND",
}

ACRONYMS = {"PO", "UK", "GB", "EU", "USA"}


POSTCODE_REGEX = re.compile(
    r"\b(GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
    re.IGNORECASE,
)


def _strip_invisible_and_emoji(text: str) -> str:
    """Remove emojis and non-printing characters while preserving letters."""
    cleaned_chars: List[str] = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("C"):
            continue
        if category == "So":
            continue
        cleaned_chars.append(char)
    return "".join(cleaned_chars)


def clean_line(s: str) -> str:
    """Clean a single line by trimming, normalizing spaces, and stripping punctuation."""
    if not s:
        return ""
    text = _strip_invisible_and_emoji(s)
    text = text.replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" \n\r\t,.")
    return text


def is_probably_uk_postcode(s: str) -> bool:
    """Return True if the input string looks like a UK postcode."""
    if not s:
        return False
    compact = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    if compact == "GIR0AA":
        return True
    return bool(re.fullmatch(r"[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}", compact))


def normalize_uk_postcode(s: str) -> str:
    """Normalize a UK postcode to uppercase with a single space before last 3 chars."""
    if not s:
        return ""
    compact = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    if not is_probably_uk_postcode(compact):
        return ""
    if compact == "GIR0AA":
        return "GIR 0AA"
    outward, inward = compact[:-3], compact[-3:]
    return f"{outward} {inward}"


def _split_on_commas(line: str) -> List[str]:
    """Split a line on commas and return cleaned parts."""
    parts = [clean_line(part) for part in line.split(",")]
    return [part for part in parts if part]


def _normalize_title_case_token(token: str) -> str:
    if not token:
        return token
    if token.upper() in ACRONYMS:
        return token.upper()
    if len(token) <= 2 and token.isalpha():
        return token.upper()
    if any(char.isdigit() for char in token):
        return token.upper()
    return token.capitalize()


def _normalize_case(text: str) -> str:
    """Title-case-ish normalization while preserving acronyms and initials."""
    tokens: List[str] = []
    for raw_token in text.split():
        if "-" in raw_token:
            parts = raw_token.split("-")
            tokens.append("-".join(_normalize_title_case_token(part) for part in parts))
        elif "'" in raw_token:
            parts = raw_token.split("'")
            tokens.append("'".join(_normalize_title_case_token(part) for part in parts))
        else:
            tokens.append(_normalize_title_case_token(raw_token))
    return " ".join(tokens)


def _normalize_name(name: str) -> str:
    """Normalize recipient name to title case while preserving initials."""
    cleaned = clean_line(name)
    return _normalize_case(cleaned)


def _normalize_address_line(line: str) -> str:
    """Normalize address lines to a consistent casing without breaking acronyms."""
    cleaned = clean_line(line)
    return _normalize_case(cleaned)


def _extract_postcode(line: str) -> tuple[str, str]:
    """Extract postcode from line if present; return remaining line and postcode."""
    match = POSTCODE_REGEX.search(line)
    if not match:
        return line, ""
    normalized = normalize_uk_postcode(match.group(1))
    remaining = POSTCODE_REGEX.sub(" ", line)
    remaining = clean_line(remaining)
    return remaining, normalized


def _is_country_line(line: str) -> bool:
    cleaned = re.sub(r"[^A-Za-z\s]", "", line).upper().strip()
    return cleaned in UK_COUNTRY_VARIANTS


def _assign_address_fields(lines: List[str]) -> Dict[str, str]:
    """
    Assign address_line_1, address_line_2, town_city, county based on a
    deterministic heuristic.

    Known limitation: extra middle lines beyond the first two and last two are
    appended to address_line_2 to avoid dropping data.
    """
    address_line_1 = ""
    address_line_2 = ""
    town_city = ""
    county = ""

    if not lines:
        return {
            "address_line_1": address_line_1,
            "address_line_2": address_line_2,
            "town_city": town_city,
            "county": county,
        }

    if len(lines) == 1:
        address_line_1 = lines[0]
    elif len(lines) == 2:
        address_line_1, town_city = lines
    elif len(lines) == 3:
        address_line_1, address_line_2, town_city = lines
    else:
        address_line_1 = lines[0]
        address_line_2 = lines[1]
        town_city = lines[-2]
        county = lines[-1]
        middle = lines[2:-2]
        if middle:
            address_line_2 = ", ".join([address_line_2, *middle])

    return {
        "address_line_1": address_line_1,
        "address_line_2": address_line_2,
        "town_city": town_city,
        "county": county,
    }


def parse_batch(raw_text: str) -> List[Dict[str, str]]:
    """
    Parse a block of raw text containing multiple addresses separated by blank lines.

    Returns a list of dictionaries suitable for Click & Drop XLSX export.
    """
    if not raw_text:
        return []

    records: List[Dict[str, str]] = []
    chunks = [chunk for chunk in re.split(r"\n\s*\n+", raw_text.strip()) if chunk.strip()]

    for chunk in chunks:
        raw_lines = [clean_line(line) for line in chunk.splitlines()]
        raw_lines = [line for line in raw_lines if line]
        if not raw_lines:
            continue

        full_name = _normalize_name(raw_lines[0])
        address_lines_raw = raw_lines[1:]

        postcode = ""
        country = "UNITED KINGDOM"
        processed_lines: List[str] = []

        for raw_line in address_lines_raw:
            for part in _split_on_commas(raw_line):
                if _is_country_line(part):
                    country = "UNITED KINGDOM"
                    continue

                remaining, extracted_postcode = _extract_postcode(part)
                if extracted_postcode:
                    postcode = extracted_postcode
                if remaining:
                    processed_lines.append(_normalize_address_line(remaining))

        assigned = _assign_address_fields(processed_lines)

        record = {
            "full_name": full_name,
            "address_line_1": assigned["address_line_1"],
            "address_line_2": assigned["address_line_2"],
            "town_city": assigned["town_city"],
            "county": assigned["county"],
            "postcode": postcode,
            "country": country,
            "notes": "",
        }
        records.append(record)

    return records


if __name__ == "__main__":
    SAMPLE_INPUT = """
Grace O'Neil
Flat 2, 10 High Street
Stonehaven
Aberdeenshire
AB538HY
UK

Martin Wilkie
Unit 7, Riverside Estate,
Dock Road
Barry
CF644BU
United Kingdom

Jamie
1 Queen's Road, Suite 5
ME74NN

James Hannay
PO Box 12
Sa198pq
Wales

M taylor
10 The Grove
Bromley
BR5 4AR

IAIN FRENCH
2 Church Lane
St Clears
Carmarthenshire
SA198PQ
""".strip()

    print("Parsed records:")
    print(json.dumps(parse_batch(SAMPLE_INPUT), indent=2))

    print("\nPostcode normalization demo:")
    for demo in ["AB538HY", "SA198PQ", "ME74NN", "CF644BU", "BR5 4AR"]:
        print(f"{demo} -> {normalize_uk_postcode(demo)}")
