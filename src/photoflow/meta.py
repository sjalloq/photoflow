"""Read capture metadata for a batch of files with a single exiftool call.

exiftool takes roughly a quarter of a second to start; a card holds hundreds of
frames. Invoking it once per file is what makes naive importers slow, so
everything here is built around one process for the whole batch.
"""

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

TAGS = [
    "-DateTimeOriginal",
    "-SubSecTimeOriginal",
    "-CreateDate",
    "-FileModifyDate",
    "-Make",
    "-Model",
]

# exiftool's date format, and the same with a trailing timezone offset that
# FileModifyDate carries but DateTimeOriginal does not.
_FORMATS = ("%Y:%m:%d %H:%M:%S%z", "%Y:%m:%d %H:%M:%S")


@dataclass
class Frame:
    """One file on the card, with the metadata needed to place it."""

    path: Path
    captured: datetime
    subsec: str
    make: str
    model: str
    dated_from: str  # which tag the timestamp came from

    @property
    def stem(self):
        return self.path.stem

    @property
    def day(self):
        return self.captured.date()

    @property
    def timestamp(self):
        return self.captured.strftime("%Y%m%d-%H%M%S")


def require_exiftool():
    if not shutil.which("exiftool"):
        sys.exit(
            "exiftool not found — install with: sudo pacman -S perl-image-exiftool"
        )


def _parse_date(value):
    if not value:
        return None
    # A camera that has never had its clock set writes zeroes; treat as absent.
    if value.startswith("0000"):
        return None
    for fmt in _FORMATS:
        try:
            # Drop the timezone: the camera's local wall-clock time is the
            # thing being filed by, and converting it would move frames
            # between days for no gain.
            return datetime.strptime(value, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def read(paths, chunk=400):
    """Return [Frame] for the given paths, in the order given.

    Paths are passed to exiftool in chunks so a card with thousands of frames
    doesn't overflow the argument list.
    """
    require_exiftool()
    paths = [Path(p) for p in paths]
    records = {}
    for i in range(0, len(paths), chunk):
        batch = paths[i : i + chunk]
        result = subprocess.run(
            ["exiftool", "-j", "-n", "-q", *TAGS, *[str(p) for p in batch]],
            capture_output=True,
            text=True,
        )
        if not result.stdout.strip():
            sys.exit(f"exiftool returned nothing: {result.stderr.strip()}")
        for record in json.loads(result.stdout):
            records[Path(record["SourceFile"])] = record

    frames = []
    for path in paths:
        record = records.get(path)
        if record is None:
            continue
        for tag, source in (
            ("DateTimeOriginal", "exif"),
            ("CreateDate", "exif-create"),
            ("FileModifyDate", "mtime"),
        ):
            captured = _parse_date(str(record.get(tag, "")))
            if captured:
                break
        else:
            # No usable date anywhere; the filesystem is the last word.
            captured = datetime.fromtimestamp(path.stat().st_mtime)
            source = "mtime"
        frames.append(
            Frame(
                path=path,
                captured=captured,
                subsec=str(record.get("SubSecTimeOriginal", "") or ""),
                make=str(record.get("Make", "") or ""),
                model=str(record.get("Model", "") or ""),
                dated_from=source,
            )
        )
    return frames
