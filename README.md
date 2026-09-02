# photoflow

Get photographs off a camera card into an archive you can still make sense of in
twenty years, and produce a browsable mirror of it for the web, a NAS share or a
photo frame.

Built around a Ricoh GR II, but the camera is configuration rather than code.

## Install

```sh
sudo pacman -S perl-image-exiftool imagemagick rsync   # or your distro's equivalents
uv tool install git+https://github.com/sjalloq/photoflow
```

Or from a checkout:

```sh
git clone https://github.com/sjalloq/photoflow && uv tool install ./photoflow
```

`exiftool`, `magick` and `rsync` are external programs; photoflow itself has no
Python dependencies.

## How the archive is laid out

```
Archive/
  grii/                                    <- source: a camera, a scanner, a batch
    2026/
      2026-08-30_brighton-beach/
        raw/20260830-094759_R0010948.DNG
        jpg/20260830-094759_R0010948.JPG
        .photoflow.json                    <- what was copied, and its checksums
  scans/negatives/1998/1998-08_cornwall/
  imported/old-library-2011/
```

The date is in the folder name and the capture time is in the filename, so the
tree explains itself without a database. Nothing here depends on photoflow: you
can rename a shoot folder, move a year, or drop the whole thing on a NAS, and the
tools will still find their way around.

Source-first at the top level is what lets negatives and old libraries live
alongside a camera without pretending they share its date conventions.

The web tree mirrors the archive path for path:

```
Web/grii/2026/2026-08-30_brighton-beach/20260830-094759_R0010948.jpg
                                        thumbs/…
                                        index.html
```

## Use

```sh
photoflow status                       # what's on the card, what's already archived
photoflow ingest --name "brighton beach"
photoflow gallery                      # derivatives + browsable index.html
photoflow sync web                     # rsync to the NAS
```

### status

Read-only. Reports the card's frames, which capture days they span, and how many
are not yet in the archive. Run it before formatting a card in-camera.

### ingest

Copies originals into the archive. Frames are filed by the day they were *taken*,
not the day they were imported, so a card holding three days of shooting produces
three shoot folders.

- Every copy is SHA-256 verified against the source, and lands via a `.partial`
  name so an interrupted run leaves nothing a later run would mistake for
  finished work.
- Re-running is free and safe: already-imported frames are skipped. A file whose
  name matches but whose contents differ is given a new name — an original is
  never overwritten.
- **The card is never modified.** Format it in-camera when `status` says it is
  safe.
- A DNG and its JPEG are one photograph: they get one shared filename, taken from
  the RAW's timestamp, and stay paired.

`--dry-run` prints the whole plan without touching anything. `--dest` writes
somewhere other than the configured archive.

### derive

Renders resized JPEGs into the web tree:
resample in linear light, unsharp mask back in sRGB, EXIF rotation baked into the
pixels before the metadata is stripped. Presets (`web`, `frame`, `thumb`) come
from the config.

By default it renders from the camera JPEG when there is one — the GR II's own
rendering is good and it is far faster than developing the DNG. `--source raw`
forces the RAW. Outputs newer than their input are skipped, so re-running costs
almost nothing.

### gallery

`derive` plus a self-contained `index.html` per shoot: thumbnail grid, lightbox,
arrow-key navigation, light and dark. No CDN, no server, no build step — it works
opened straight off disk with `file://`. Parent `index.html` pages are written
over the year and camera folders too, so the whole tree is browsable from the top.

### sync

`rsync -a` to the targets in the config. `--delete` is opt-in and never implied.

## Configuration

`~/.config/photoflow/config.toml`, written with commented defaults on first run.
It holds the archive and web roots, the rsync targets, the camera profiles (card
label, EXIF model, which extensions are RAW and which are JPEG) and the derive
presets. Adding a second camera is a `[[cameras]]` block, not a patch.

## Tests

```sh
uv run pytest
```

Covers the parts worth being sure of: filename and folder grammar, RAW/JPEG
pairing, collision handling when the camera's counter wraps, and config
precedence. They need no card and no images.

## Licence

MIT — see [LICENSE](LICENSE).
