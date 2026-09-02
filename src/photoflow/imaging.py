"""Build the ImageMagick command that turns an original into a derivative.

Adapted from an earlier scanner script, minus its DPI handling, which matters
for a scan and means nothing for a camera frame. The two ideas worth keeping:

  * resample in linear light — ImageMagick otherwise resizes gamma-encoded
    sRGB, which darkens fine detail;
  * sharpen back in sRGB, where conventional unsharp-mask amounts apply.

`-auto-orient` runs first so the EXIF rotation is baked into the pixels before
`-strip` throws the tag away; without it, portrait frames come out sideways.
"""

import shutil
import subprocess
import sys

# radius x sigma + amount + threshold
SHARPEN = {
    "none": None,
    "light": "0x0.6+0.5+0.010",
    "medium": "0x0.7+0.8+0.008",
    "strong": "0x1.0+1.2+0.006",
}


def require_magick():
    if not shutil.which("magick"):
        sys.exit("ImageMagick not found — install with: sudo pacman -S imagemagick")


def build_command(src, dest, long_edge=None, sharpen="medium", quality=90, strip=True):
    if sharpen not in SHARPEN:
        known = ", ".join(SHARPEN)
        sys.exit(f"unknown sharpen '{sharpen}' (choose from: {known})")
    cmd = ["magick", str(src), "-auto-orient"]
    if long_edge:
        # The trailing '>' means "shrink only" — there is no detail to invent.
        cmd += ["-colorspace", "RGB", "-filter", "Lanczos"]
        cmd += ["-resize", f"{long_edge}x{long_edge}>"]
        cmd += ["-colorspace", "sRGB"]
    if SHARPEN[sharpen]:
        cmd += ["-unsharp", SHARPEN[sharpen]]
    if strip:
        cmd += ["-strip"]
    if dest.suffix.lower() in (".jpg", ".jpeg"):
        cmd += ["-quality", str(quality), "-sampling-factor", "4:4:4"]
    cmd += ["-depth", "8", str(dest)]
    return cmd


def convert(src, dest, **kwargs):
    """Render one derivative. Returns None on success, an error string if not."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(src, dest, **kwargs)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return result.stderr.strip() or f"magick exited {result.returncode}"
    return None
