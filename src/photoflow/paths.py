"""The archive path grammar, and the rules for naming what lands in it.

Layout is source -> year -> shoot, with originals split by kind:

    <archive>/<camera>/<YYYY>/<YYYY-MM-DD>[_<name>]/raw/...
                                                   /jpg/...

The date lives in the folder name and the capture time lives in the filename, so
the tree is self-describing: no database is needed to know when anything was
taken, and a folder can be renamed or moved without breaking anything.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST = ".photoflow.json"

# YYYY-MM-DD, optionally followed by _some-label
SHOOT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:_(.+))?$")


def slugify(name):
    """Fold a free-text shoot label into something safe for a folder name."""
    slug = re.sub(r"[^\w-]+", "-", name.strip().lower())
    return slug.strip("-")


def year_dir(archive, camera_id, day):
    return Path(archive) / camera_id / f"{day.year:04d}"


def find_shoot(archive, camera_id, day):
    """Return an existing folder for this capture day, or None.

    Matching on the date prefix alone means a later run with a different --name
    joins the day that's already there instead of forking it in two.
    """
    parent = year_dir(archive, camera_id, day)
    if not parent.is_dir():
        return None
    prefix = day.isoformat()
    for entry in sorted(parent.iterdir()):
        if not entry.is_dir():
            continue
        match = SHOOT_RE.match(entry.name)
        if match and match.group(1) == prefix:
            return entry
    return None


def shoot_dir(archive, camera_id, day, name=None):
    """The folder this capture day belongs in, existing or not yet created."""
    existing = find_shoot(archive, camera_id, day)
    if existing:
        return existing
    label = slugify(name) if name else ""
    stem = f"{day.isoformat()}_{label}" if label else day.isoformat()
    return year_dir(archive, camera_id, day) / stem


def shoot_day(path):
    """The capture date a shoot folder encodes, or None if it isn't one."""
    match = SHOOT_RE.match(Path(path).name)
    if not match:
        return None
    from datetime import date

    return date.fromisoformat(match.group(1))


@dataclass
class Plan:
    """One source file and where it is going."""

    frame: object
    dest: Path
    kind: str
    status: str = "new"  # new | skip | conflict


@dataclass
class Shoot:
    """A capture day's worth of files, resolved to a destination folder."""

    day: object
    directory: Path
    plans: list = field(default_factory=list)

    @property
    def new(self):
        return [p for p in self.plans if p.status == "new"]


def _base_stem(frame, subsec):
    """`YYYYMMDD-HHMMSS_R0010948`, with sub-second precision when recorded."""
    stamp = frame.timestamp
    if subsec:
        stamp = f"{stamp}.{subsec}"
    return f"{stamp}_{frame.stem}"


def plan_shoots(frames, camera, archive, name=None):
    """Group frames into shoots and decide each file's destination name.

    Files sharing an original stem are one photograph (the DNG and its JPEG), so
    they are named together from the RAW's timestamp and stay paired forever.
    """
    by_day = {}
    for frame in frames:
        if camera.kind(frame.path) is None:
            continue
        by_day.setdefault(frame.day, []).append(frame)

    shoots = []
    for day in sorted(by_day):
        directory = shoot_dir(archive, camera.id, day, name)
        shoot = Shoot(day=day, directory=directory)

        # Pair by the camera's own stem, within its own DCIM folder: the
        # counter wraps at 9999, so the same stem in two folders is two
        # different photographs and must not be merged into one.
        groups = {}
        for frame in by_day[day]:
            groups.setdefault((frame.path.parent, frame.path.stem), []).append(frame)

        taken = set()
        for key in sorted(groups):
            members = groups[key]
            # The RAW carries the authoritative capture time; if there is no
            # RAW, the JPEG's will do.
            lead = next(
                (f for f in members if camera.kind(f.path) == "raw"), members[0]
            )
            base = _base_stem(lead, lead.subsec)
            # Two DCIM folders can hold the same camera stem once the counter
            # wraps; suffix rather than let one silently shadow the other.
            candidate, n = base, 1
            while candidate in taken:
                n += 1
                candidate = f"{base}-{n}"
            taken.add(candidate)

            for frame in members:
                kind = camera.kind(frame.path)
                dest = (
                    directory / kind / f"{candidate}{frame.path.suffix.upper()}"
                )
                shoot.plans.append(Plan(frame=frame, dest=dest, kind=kind))
        shoots.append(shoot)
    return shoots
