"""Render the web/browse mirror of the archive.

The archive holds originals and is never touched; everything here writes into
the web root at the same relative path, so `<archive>/grii/2026/2026-08-30/`
becomes `<web>/grii/2026/2026-08-30/`. That parallel shape is what makes the
result mountable as a share, pointable at a photo frame, or importable into
Immich without any further mapping.
"""

import concurrent.futures
from pathlib import Path

from . import imaging, paths

SUFFIXES = {".dng", ".jpg", ".jpeg", ".tif", ".tiff", ".png", ".heic"}


def sources(directory, prefer="auto"):
    """The originals in one shoot folder, one entry per photograph.

    'auto' takes the camera JPEG when there is one: the GR II's own rendering
    is good, and reading it is many times faster than developing the DNG.
    """
    directory = Path(directory)
    raw = {p.stem: p for p in sorted((directory / "raw").glob("*")) if p.suffix.lower() in SUFFIXES}
    jpg = {p.stem: p for p in sorted((directory / "jpg").glob("*")) if p.suffix.lower() in SUFFIXES}
    if not raw and not jpg:
        # A folder of loose files — legacy imports and scans look like this.
        loose = [p for p in sorted(directory.glob("*")) if p.is_file() and p.suffix.lower() in SUFFIXES]
        return {p.stem: p for p in loose}

    chosen = {}
    for stem in sorted(set(raw) | set(jpg)):
        if prefer == "raw":
            chosen[stem] = raw.get(stem) or jpg[stem]
        elif prefer == "jpg":
            chosen[stem] = jpg.get(stem) or raw[stem]
        else:
            chosen[stem] = jpg.get(stem) or raw[stem]
    return chosen


# Directories that are part of a shoot rather than shoots in their own right.
INTERNAL = {"raw", "jpg", "thumbs", "web"}


def shoot_dirs(roots, archive):
    """Expand the given paths into the shoot folders that hold originals.

    Descent stops at a shoot: its own raw/ and jpg/ subdirectories are full of
    images, but they are that shoot's halves, not two more shoots.
    """
    found, seen = [], set()
    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.exists():
            print(f"skipping missing path: {root}")
            continue
        stack = [root]
        while stack:
            directory = stack.pop()
            if directory in seen:
                continue
            seen.add(directory)
            if sources(directory):
                found.append(directory)
                continue
            stack += [
                child
                for child in directory.iterdir()
                if child.is_dir() and child.name not in INTERNAL
            ]
    return sorted(found)


def out_dir(shoot, archive, web, explicit=None):
    """Mirror the shoot's position under the archive into the web root."""
    if explicit:
        return Path(explicit).expanduser()
    archive = Path(archive).expanduser().resolve()
    try:
        return Path(web).expanduser() / shoot.relative_to(archive)
    except ValueError:
        # Outside the archive (e.g. a folder ingested with --dest): keep the
        # derivatives beside their originals rather than guessing.
        return shoot / "web"


def render(shoot, dest, preset, prefer="auto", subdir=None, jobs=4, force=False, report=print):
    """Render one shoot's originals into `dest`. Returns the output paths."""
    imaging.require_magick()
    dest = dest / subdir if subdir else dest
    chosen = sources(shoot, prefer)
    if not chosen:
        return []

    jobs_list, outputs = [], []
    for stem, src in sorted(chosen.items()):
        out = dest / f"{stem}.jpg"
        outputs.append(out)
        # Re-running should be nearly free, so skip anything already current.
        if not force and out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
            continue
        jobs_list.append((src, out))

    if not jobs_list:
        report(f"{shoot.name}: {len(outputs)} derivative(s) already current")
        return outputs

    report(f"{shoot.name}: {len(jobs_list)} of {len(outputs)} to render -> {dest}")

    def one(pair):
        src, out = pair
        error = imaging.convert(
            src,
            out,
            long_edge=preset.get("long_edge"),
            sharpen=preset.get("sharpen", "medium"),
            quality=preset.get("quality", 90),
        )
        return f"  FAILED {src.name}: {error}" if error else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for line in pool.map(one, jobs_list):
            if line:
                report(line)
    return outputs
