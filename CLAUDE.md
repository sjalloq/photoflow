# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

photoflow ingests photographs from a camera card into a self-describing archive
and renders a browsable mirror of it (resized JPEGs plus static galleries) for a
NAS, the web, or a photo frame. First camera is a Ricoh GR II; the camera is
configuration, not code.

See README.md for user-facing behaviour. This file covers what a future session
needs to *change* the code safely.

## Development Commands

```bash
uv sync --extra dev              # create/refresh .venv
uv run pytest -q                 # unit tests: no card, no images needed
uv run photoflow status          # smoke test against a real card
uv tool install . --force        # install to PATH as `photoflow`
```

Develop with `uv run photoflow …` (runs the working copy). `uv tool install` is
for the installed copy the user actually uses — re-run it after changes land.

## Architecture

```
cli.py       argparse dispatch; the only module that knows about flags
config.py    tomllib load, DEFAULTS merge, Camera/Config objects
card.py      find the SD card (lsblk by label), mount/unmount via udisksctl
meta.py      ONE batched exiftool call -> [Frame]
paths.py     the archive path grammar; plan_shoots() decides every destination
ingest.py    classify (new/skip/conflict), verified copy, .photoflow.json manifest
imaging.py   the ImageMagick command builder (from ~/.local/bin/scanderive)
derive.py    walk the archive, mirror it into the web root
gallery.py   render derivatives + self-contained index.html pages
sync.py      rsync wrapper
```

**Layering:** `paths.py` decides *where things go* and is pure — no I/O, no
subprocesses. `ingest.py` decides *what to do about it* and touches disk. Keep
that split: it is what makes the naming rules testable without a card.

## Invariants — do not break these

1. **The card is read-only.** Nothing writes to, deletes from, or modifies a
   mounted card. There is no `--delete-after-import`; the user formats in-camera
   once `status` says it is safe.
2. **Ingest is idempotent.** Running twice must be indistinguishable from running
   once. Destination names are derived from capture time, so a re-ingest produces
   the same names and skips them.
3. **An original is never overwritten.** A name clash with genuinely different
   content (verified by SHA-256, not size) gets a `-2` suffix.
4. **Copies land via `.partial` and are SHA-256 verified** before being renamed
   into place, so an interrupted run leaves nothing a later run mistakes for
   finished work. This has been exercised for real — do not "simplify" it away.
5. **A DNG and its JPEG are one photograph**: one shared stem, taken from the
   RAW's timestamp. They must stay paired through any renaming change.
6. **`-auto-orient` runs before `-strip`.** Otherwise `--strip` discards the tag
   that said "rotate me" while the pixels never move, and portrait frames come
   out silently sideways. 29 of the 54 test frames are portrait; this is not a
   corner case.
7. **The tree needs no database.** Date in the folder name, capture time in the
   filename. `.photoflow.json` is an audit trail — deleting it costs a re-hash,
   nothing more. Never make it load-bearing.

## Gotchas already paid for

- **EXIF `Model` for the GR II is `GR II`, not `RICOH GR II`.** `Make` carries
  the "RICOH IMAGING COMPANY, LTD." part.
- **Group frames by `(parent_dir, stem)`, never by stem alone.** The camera's
  counter wraps at 9999, so two DCIM folders can hold the same `R0010948` — a
  stem-only key merges two different photographs into one and silently drops the
  second. There is a regression test for this.
- **`derive.shoot_dirs()` must prune `raw/`, `jpg/`, `thumbs/`, `web/`** when
  descending. Those directories are full of images but they are a shoot's parts,
  not more shoots. Descent stops as soon as a directory looks like a shoot.
- **exiftool is called once per batch, not once per file.** It takes ~0.25s to
  start; a card holds hundreds of frames. Preserve the batching in `meta.read()`.
- **Resample in linear RGB, sharpen back in sRGB.** ImageMagick otherwise resizes
  gamma-encoded sRGB, which darkens fine detail. Inherited from `scanderive`.
- **Timestamps are used as the camera wrote them, with no timezone conversion.**
  Converting would move frames between days for no gain.

## Testing

`tests/` covers the pure logic — naming, RAW/JPEG pairing, counter-wrap
collisions, shoot-folder reuse, config precedence. `tests/conftest.py` has a
`frame()` helper that fabricates a `Frame` so no real file is needed. Anything
you can express as "given these frames, where should they land" belongs there.

Verifying against a real card (a GR II card of 170 files across two days was used
for the initial build):

```bash
photoflow status                    # detects the card by volume label
photoflow ingest --dest /tmp/A -n   # inspect the plan
photoflow ingest --dest /tmp/A      # then re-run: must copy nothing
photoflow gallery                   # open the index.html from file://
```

Check portrait frames survive: an EXIF orientation-6 source is 4928x3264
(landscape pixels) and must derive to a portrait 1696x2560.

## Conventions

- Python ≥3.11 (stdlib `tomllib`), **no runtime dependencies**. `exiftool`,
  `magick` and `rsync` are external binaries; check with `shutil.which` and exit
  with the pacman command that installs them.
- Comments explain *why*, especially where a decision looks arbitrary but was
  paid for (see Gotchas). Don't narrate what the code plainly does.
- User-facing output is plain `print` — no progress bars, no colour library.
- New camera support should be a `[[cameras]]` block in the config, not code. If
  something can't be expressed that way, that's the thing worth discussing first.

## Related

`~/.local/bin/scanderive` and `~/.local/bin/scanphoto` are the older standalone
scan tools. `imaging.py` is a *copy* of scanderive's command builder, minus its
DPI handling (meaningless for a camera frame); the two are free to diverge.
Scanned negatives are expected to land in the archive as their own source
(`scans/negatives/…`) rather than under a camera.
