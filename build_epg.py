#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OPEN_EPG_URL = "https://www.open-epg.com/files/lithuania1.xml"
RODO_URL = "https://rodo.lt/kanalai/lietuvos-ryto-tv"
OFFICIAL_URL = "https://www.lietuvosryto.tv/tv-programa"

CHANNEL_ID = "Lietuvos ryto televizija.lt"
OUTPUT_FILE = "lt_epg.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}

LT_MONTHS = {
    "sausio": 1,
    "vasario": 2,
    "kovo": 3,
    "balandžio": 4,
    "gegužės": 5,
    "birželio": 6,
    "liepos": 7,
    "rugpjūčio": 8,
    "rugsėjo": 9,
    "spalio": 10,
    "lapkričio": 11,
    "gruodžio": 12,
}

TIME_RE = re.compile(r"^(?P<h>[0-2]?\d)[\.: ](?P<m>[0-5]\d)\s+(?P<title>.+)$")
ISO_DATE_RE = re.compile(r"^(20\d{2})-(\d{2})-(\d{2})$")
OFFICIAL_DATE_RE = re.compile(
    r"(?P<year>20\d{2})\s*m\.\s*"
    r"(?P<month>[A-Za-zĄČĘĖĮŠŲŪŽąčęėįšųūž]+)\s+"
    r"(?P<day>\d{1,2})\s*d\.",
    re.IGNORECASE,
)


def get_text(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def clean_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return lines


def normalise_time(line: str):
    # Handles 05:00, 05.00, 05 00, and the occasional 0.00.
    m = TIME_RE.match(line)
    if not m:
        return None
    hour = int(m.group("h"))
    minute = int(m.group("m"))
    if hour > 23:
        return None
    return hour, minute, m.group("title").strip()


def parse_rodo(html: str) -> list[tuple[datetime, str]]:
    lines = clean_lines(html)
    current_date = None
    out = []

    for line in lines:
        dm = ISO_DATE_RE.match(line)
        if dm:
            current_date = datetime(
                int(dm.group(1)), int(dm.group(2)), int(dm.group(3))
            ).date()
            continue

        if current_date is None:
            continue

        t = normalise_time(line)
        if not t:
            continue

        hour, minute, title = t
        if title:
            out.append(
                (datetime.combine(current_date, datetime.min.time()).replace(
                    hour=hour, minute=minute
                ), title)
            )

    return dedupe_and_sort(out)


def parse_official(html: str) -> list[tuple[datetime, str]]:
    lines = clean_lines(html)
    current_date = None
    out = []

    for line in lines:
        dm = OFFICIAL_DATE_RE.search(line)
        if dm:
            month_name = dm.group("month").lower()
            month = LT_MONTHS.get(month_name)
            if month:
                current_date = datetime(
                    int(dm.group("year")), month, int(dm.group("day"))
                ).date()
            continue

        if current_date is None:
            continue

        t = normalise_time(line)
        if not t:
            continue

        hour, minute, title = t
        if title:
            out.append(
                (datetime.combine(current_date, datetime.min.time()).replace(
                    hour=hour, minute=minute
                ), title)
            )

    return dedupe_and_sort(out)


def dedupe_and_sort(items):
    seen = set()
    out = []
    for dt, title in sorted(items, key=lambda x: x[0]):
        key = (dt, title)
        if key not in seen:
            seen.add(key)
            out.append((dt, title))
    return out


def get_rytas_schedule() -> list[tuple[datetime, str]]:
    results = []

    # Rodo normally has a rolling week including future days.
    try:
        print("Fetching Lietuvos ryto TV schedule from rodo.lt ...")
        results = parse_rodo(get_text(RODO_URL))
        print(f"rodo.lt parsed entries: {len(results)}")
    except Exception as e:
        print(f"rodo.lt failed: {e}", file=sys.stderr)

    # Official site is the fallback and can also supplement missing dates.
    try:
        print("Fetching official Lietuvos ryto TV schedule ...")
        official = parse_official(get_text(OFFICIAL_URL))
        print(f"official parsed entries: {len(official)}")
        if official:
            merged = {(dt, title): (dt, title) for dt, title in results}
            for item in official:
                merged[item] = item
            results = dedupe_and_sort(list(merged.values()))
    except Exception as e:
        print(f"official site failed: {e}", file=sys.stderr)

    if not results:
        raise RuntimeError(
            "Could not parse any Lietuvos ryto TV programmes from either source."
        )

    return results


def xmltv_stamp(local_dt: datetime) -> str:
    tz = ZoneInfo("Europe/Vilnius")
    aware = local_dt.replace(tzinfo=tz)
    return aware.strftime("%Y%m%d%H%M%S %z")


def ensure_channel(root: ET.Element):
    for ch in root.findall("channel"):
        if ch.get("id") == CHANNEL_ID:
            return
    ch = ET.Element("channel", {"id": CHANNEL_ID})
    dn = ET.SubElement(ch, "display-name")
    dn.text = CHANNEL_ID
    # Channels conventionally appear before programme elements.
    first_programme = next(
        (i for i, node in enumerate(list(root)) if node.tag == "programme"),
        len(root),
    )
    root.insert(first_programme, ch)


def replace_rytas_programmes(root: ET.Element, schedule):
    for p in list(root.findall("programme")):
        if p.get("channel") == CHANNEL_ID:
            root.remove(p)

    for i, (start_dt, title) in enumerate(schedule):
        if i + 1 < len(schedule):
            stop_dt = schedule[i + 1][0]
            # Avoid absurdly long programme blocks if a source has a gap.
            if stop_dt <= start_dt or stop_dt - start_dt > timedelta(hours=8):
                stop_dt = start_dt + timedelta(hours=1)
        else:
            stop_dt = start_dt + timedelta(hours=1)

        p = ET.Element(
            "programme",
            {
                "start": xmltv_stamp(start_dt),
                "stop": xmltv_stamp(stop_dt),
                "channel": CHANNEL_ID,
            },
        )
        title_el = ET.SubElement(p, "title", {"lang": "lt"})
        title_el.text = title
        root.append(p)


def main():
    print("Downloading Open-EPG Lithuania base XML ...")
    r = requests.get(OPEN_EPG_URL, headers=HEADERS, timeout=45)
    r.raise_for_status()

    root = ET.fromstring(r.content)
    ensure_channel(root)

    schedule = get_rytas_schedule()
    replace_rytas_programmes(root, schedule)

    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

    print(f"Wrote {OUTPUT_FILE}")
    print(f"Lietuvos ryto TV programmes added: {len(schedule)}")
    print(f"First: {schedule[0][0]} - {schedule[0][1]}")
    print(f"Last : {schedule[-1][0]} - {schedule[-1][1]}")


if __name__ == "__main__":
    main()
