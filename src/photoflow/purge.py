"""Delete the frames a review rejected: `photoflow purge`.

A reject in the browser only writes `"reject": true` into the day's
`review.json`; the files stay where they are so the decision can be reversed
with a keystroke. This is the step that makes it final. It is a separate,
deliberate command rather than a button in the UI because it removes
originals, and nothing else in photoflow does that.

`victims()` is pure and decides what goes; `run()` deletes it. Everything that
shares the rejected stem is removed — the DNG, the JPEG and both derivatives —
because a DNG and its JPEG are one photograph. The stem is then dropped from
`frames` in review.json and appended to `purged`, so the file still tells the
story of the day. That list is an audit trail only: nothing reads it.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from . import derive

REVIEW = "review.json"
# Where a stem's files can live inside a day folder; "." is a legacy folder of
# loose originals, which have no raw/ or jpg/ split.
PARTS = ("raw", "jpg", "thumb", "web", ".")


def load_state(day):
    path = Path(day) / REVIEW
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text())
    except ValueError:
        sys.exit(f"{path} is not valid JSON; fix it (or run `photoflow review`) before purging")
    if not isinstance(state, dict) or not isinstance(state.get("frames"), dict):
        return None
    return state


def rejected(state):
    """The stems a review marked for deletion."""
    if not state:
        return []
    return sorted(s for s, d in state["frames"].items() if isinstance(d, dict) and d.get("reject"))


def victims(day, stems):
    """Every file in the day folder that belongs to one of these stems.

    Matching is by exact stem, never by prefix: `R0010948` must not sweep up
    `R0010948-2`, which is a different photograph that clashed on its name.
    """
    day = Path(day)
    stems = set(stems)
    found = []
    for part in PARTS:
        folder = day / part
        if not folder.is_dir():
            continue
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.stem in stems and p.suffix.lower() in derive.SUFFIXES:
                found.append(p)
    return found


def _save(day, state, stems):
    for stem in stems:
        state["frames"].pop(stem, None)
    purged = state.get("purged")
    if not isinstance(purged, list):
        purged = []
    stamp = datetime.now().isoformat(timespec="seconds")
    purged.extend({"id": s, "at": stamp} for s in stems)
    state["purged"] = purged
    path = Path(day) / REVIEW
    tmp = path.with_suffix(".json.partial")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def run(days, dry_run=False, assume_yes=False, report=print):
    """Delete the rejected frames in each day folder. Returns an exit status."""
    plan = []
    total = 0
    for day in days:
        day = Path(day)
        state = load_state(day)
        stems = rejected(state)
        if not stems:
            continue
        files = victims(day, stems)
        plan.append((day, state, stems, files))
        total += len(files)
        report(f"{day}: {len(stems)} rejected frame(s), {len(files)} file(s)")
        for p in files:
            report(f"  {p.relative_to(day)}")

    if not plan:
        report("nothing is marked for deletion")
        return 0
    if dry_run:
        report(f"\n{total} file(s) would be deleted (dry run)")
        return 0
    if not assume_yes:
        if not sys.stdin.isatty():
            sys.exit("refusing to delete without confirmation; pass --yes")
        answer = input(f"\nDelete these {total} file(s)? This cannot be undone [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            report("nothing deleted")
            return 1

    deleted = 0
    for day, state, stems, files in plan:
        for p in files:
            p.unlink()
            deleted += 1
        _save(day, state, stems)
    report(f"{deleted} file(s) deleted")
    return 0
