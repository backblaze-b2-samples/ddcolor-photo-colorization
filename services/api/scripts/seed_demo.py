"""Seed the Photo Library with public-domain black-and-white photographs.

    pnpm seed:demo            # ingest the 8 demo photos into colorization/grayscale/
    pnpm seed:demo --dry-run  # list what would be fetched, write nothing

Each photo is a public-domain historical photograph on Wikimedia Commons
(streets, buildings, transport and landscapes). The author, licence and source page
of every image are recorded per photo below (from the Commons API) and written to
the uploaded object as S3 user metadata (x-amz-meta-author, -license, -source-url,
-credit). Images are fetched at 1280 px wide (a Commons-rendered derivative of
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
from dataclasses import dataclass
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(API_ROOT.parents[1] / ".env")

from app.repo import b2_io  # noqa: E402
from app.service import keys  # noqa: E402
from app.service.upload import check_color  # noqa: E402

CHECKED = "2026-11-05"
USER_AGENT = "b2ai-ddcolor-photo-colorization-seed/1.0 (Backblaze B2 sample app)"
WIDTH = 1280

@dataclass(frozen=True)
class DemoPhoto:
    filename: str  # object filename under colorization/grayscale/
    title: str  # Commons file title
    context: str  # year / subject
    author: str  # Commons `Artist` field
    licence: str  # Commons `LicenseShortName` field
    credit: str  # Commons `Credit` field (where the file came from)


# Author, licence and credit come from each file's Commons API extmetadata,
# read on CHECKED. Every file currently carries the "Public domain" tag, but each
# is recorded from its own page, not assumed.
DEMO_PHOTOS: list[DemoPhoto] = [
    DemoPhoto(
        "arundel-station-1910.jpg",
        "Arundel station and train.jpg",
        "1910, railway station",
        "Unknown contract photographer for the picture postcard publisher",
        "Public domain",
        "Widely distributed contemporary picture postcards",
    ),
    DemoPhoto(
        "canadian-pacific-5121-1944.jpg",
        "Canadian Pacific 5121 Burnaby, British Columbia 1944.jpg",
        "1944, steam locomotive",
        "Andy Morin",
        "Public domain",
        "railpictures.ca",
    ),
    DemoPhoto(
        "hanoi-street-1940.jpg",
        "Hanoi, French Indochina ca. 1940.jpg",
        "c. 1940, street",
        "Unknown author, shot before 1945",
        "Public domain",
        "Flickr (photo 13183090315)",
    ),
    DemoPhoto(
        "mcdonald-lake-glacier-1941.jpg",
        "McDonald Lake, Glacier National Park 19.jpg",
        "1941, landscape",
        "Ansel Adams",
        "Public domain",
        "US National Archives",
    ),
    DemoPhoto(
        "vernal-fall-watkins-1858.jpg",
        "Watkin - Vernal Fall.jpg",
        "1858, waterfall",
        "Carleton Watkins",
        "Public domain",
        "Dialog Among Giants: Carleton Watkins (2008), J. Paul Getty Center",
    ),
    DemoPhoto(
        "spring-showers-new-york-1900.jpg",
        "Alfred Stieglitz - Spring Showers, New York - Cleveland Museum of Art.jpg",
        "1900, street in the rain",
        # Commons leaves the Artist field empty; the file title names the photographer.
        "Alfred Stieglitz (from the Commons file title)",
        "Public domain",
        "Cleveland Museum of Art",
    ),
    DemoPhoto(
        "view-from-round-top-1870s.jpg",
        "43. View from Round Top.jpg",
        "1873-1883, landscape",
        "Carleton Watkins",
        "Public domain",
        "National Library of Wales",
    ),
    DemoPhoto(
        "olivos-level-crossing-1954.jpg",
        "Av maipu pasonivel olivos 1954.jpg",
        "1954, avenue",
        "Unknown",
        "Public domain",
        "Historia de Vicente Lopez",
    ),
]


def source_page(title: str) -> str:
    return "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(title.replace(" ", "_"))


def download_url(title: str) -> str:
    quoted = urllib.parse.quote(title.replace(" ", "_"))
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quoted}?width={WIDTH}"


def attribution(photo: DemoPhoto) -> dict[str, str]:
    """Per-photo attribution stored as S3 user metadata (ASCII only)."""
    values = {
        "author": photo.author,
        "license": photo.licence,
        "source-url": source_page(photo.title),
        "credit": photo.credit,
    }
    return {k: v.encode("ascii", "ignore").decode() for k, v in values.items()}


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
    for photo in DEMO_PHOTOS:
        key = f"{keys.grayscale_prefix()}{photo.filename}"
        out(
            f"{key}\n    source: {source_page(photo.title)}\n"
            f"    author: {photo.author}\n"
            f"    licence: {photo.licence} (Commons tag, checked {CHECKED}; {photo.context})"
        )
        if args.dry_run:
            continue
        if key in existing and not args.force:
            out("    skipped: already ingested")
            continue
        data = fetch(download_url(photo.title))
        b2_io.put_object_bytes(key, data, "image/jpeg", metadata=attribution(photo))
        flag = check_color(key)
        out(f"    ingested {len(data):,} bytes (was_color={flag})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
