"""Seed the Photo Library with public-domain black-and-white photographs.

    pnpm seed:demo            # ingest the 8 demo photos into colorization/grayscale/
    pnpm seed:demo --dry-run  # list what would be fetched, write nothing

Each photo is a public-domain historical photograph on Wikimedia Commons
(streets, buildings, transport and landscapes). The source page and licence of
every image are recorded below and verified with the Commons API before
inclusion. Images are fetched at 1280 px wide (a Commons-rendered derivative of
the public-domain original) so the default demo stays small; nothing binary is
committed to the repository.

Uploads go through the app's own repo layer: the same S3 client (custom user
agent `b2ai-ddcolor-photo-colorization`), the same key layout, and the same
ingest colour check Bulk Ingest runs. Existing keys are skipped unless --force.
"""

from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(API_ROOT.parents[1] / ".env")

from app.repo import b2_io  # noqa: E402
from app.service import keys  # noqa: E402
from app.service.upload import check_color  # noqa: E402

LICENSE = "Public domain (Wikimedia Commons licence tag, checked 2026-11-04)"
USER_AGENT = "b2ai-ddcolor-photo-colorization-seed/1.0 (Backblaze B2 sample app)"
WIDTH = 1280

# (object filename, Commons file title, year/context)
DEMO_PHOTOS: list[tuple[str, str, str]] = [
    ("arundel-station-1910.jpg", "Arundel station and train.jpg", "1910, railway station"),
    (
        "canadian-pacific-5121-1944.jpg",
        "Canadian Pacific 5121 Burnaby, British Columbia 1944.jpg",
        "1944, steam locomotive",
    ),
    ("hanoi-street-1940.jpg", "Hanoi, French Indochina ca. 1940.jpg", "c. 1940, street"),
    (
        "mcdonald-lake-glacier-1941.jpg",
        "McDonald Lake, Glacier National Park 19.jpg",
        "1941, landscape",
    ),
    ("vernal-fall-watkins-1858.jpg", "Watkin - Vernal Fall.jpg", "1858, waterfall"),
    (
        "spring-showers-new-york-1900.jpg",
        "Alfred Stieglitz - Spring Showers, New York - Cleveland Museum of Art.jpg",
        "1900, street in the rain",
    ),
    ("view-from-round-top-1870s.jpg", "43. View from Round Top.jpg", "1873-1883, landscape"),
    ("olivos-level-crossing-1954.jpg", "Av maipu pasonivel olivos 1954.jpg", "1954, avenue"),
]


def source_page(title: str) -> str:
    return "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(title.replace(" ", "_"))


def download_url(title: str) -> str:
    quoted = urllib.parse.quote(title.replace(" ", "_"))
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quoted}?width={WIDTH}"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def out(message: str) -> None:
    sys.stdout.write(message + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="list, do not upload")
    parser.add_argument("--force", action="store_true", help="re-upload existing keys")
    args = parser.parse_args()

    existing = {o["Key"] for o in ([] if args.dry_run else b2_io.list_prefix(keys.grayscale_prefix()))}
    for filename, title, context in DEMO_PHOTOS:
        key = f"{keys.grayscale_prefix()}{filename}"
        out(f"{key}\n    source: {source_page(title)}\n    licence: {LICENSE} ({context})")
        if args.dry_run:
            continue
        if key in existing and not args.force:
            out("    skipped: already ingested")
            continue
        data = fetch(download_url(title))
        b2_io.put_object_bytes(key, data, "image/jpeg")
        flag = check_color(key)
        out(f"    ingested {len(data):,} bytes (was_color={flag})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
