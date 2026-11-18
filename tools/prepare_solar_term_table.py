"""Refresh the bundled Gregorian dates from the Hong Kong Observatory year tables."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from pathlib import Path
import re
import time
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://www.hko.gov.hk/en/gts/time/calendar/text/files/T{}e.txt'
INDEX = 'https://www.hko.gov.hk/en/gts/time/conversion.htm'
ROW = re.compile(r'^(\d{4})/(\d{1,2})/(\d{1,2})\s+.+?\b(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+([A-Za-z][A-Za-z &-]+?)\s*$', re.I)


def read_year(year):
    cache = ROOT / 'artifacts' / 'hko-calendar' / f'{year}.txt'
    if not cache.exists():
        for attempt in range(3):
            try:
                with urlopen(SOURCE.format(year), timeout=20) as response:
                    content = response.read()
                if not content.lstrip().startswith(b'Gregorian-Lunar'):
                    raise ValueError(f'Unexpected response for {year}')
                cache.write_bytes(content)
                break
            except (OSError, ValueError):
                if attempt == 2:
                    raise
                time.sleep(1 + attempt)
    dates = []
    for line in cache.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        match = ROW.fullmatch(line.strip())
        if match:
            dates.append(datetime.date(*map(int, match.groups()[:3])))
    if len(dates) != 24 or any(d.year != year or d.month != i // 2 + 1 for i, d in enumerate(dates)):
        raise ValueError(f'{year} has an incomplete or unordered solar-term table: {dates}')
    return ''.join(f'{day.day:02}' for day in dates)


if __name__ == '__main__':
    (ROOT / 'artifacts' / 'hko-calendar').mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        years = list(pool.map(read_year, range(1901, 2101)))
    output = ROOT / 'assets' / 'almanac' / 'solar-terms.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {'source': 'Hong Kong Observatory', 'url': INDEX, 'first_year': 1901, 'years': years}
    output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(f'{len(years) * 24} solar-term dates written to {output}')
