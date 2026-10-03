"""Summarise a folder of originals whose provenance has been lost.

An archive accumulates folders like `to_sort/tmp/` — files copied off a card
years ago with no note of which camera or which trip. The only reliable record
left is the EXIF inside each file, so this module groups frames by the body
that shot them and the day they were shot, which is all that is needed to
decide where in the archive they belong.

Pure: takes [Frame], returns groups. The exiftool call and the printing live in
meta.py and cli.py respectively, so the grouping can be tested without files.
"""

from collections import Counter
from dataclasses import dataclass, field

# Everything exiftool reads a capture date out of that a camera or scanner is
# likely to have produced. Deliberately wider than any one camera profile: the
# point of a survey is that the camera is not yet known.
IMAGE_EXT = {
    ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff", ".png",
    ".dng", ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".raf", ".orf", ".rw2", ".pef", ".srw", ".x3f", ".3fr", ".iiq", ".mos",
}


@dataclass
class Group:
    """Frames from one physical camera body."""

    make: str
    model: str
    serial: str
    frames: list = field(default_factory=list)

    @property
    def label(self):
        model = self.model or "(no EXIF model)"
        # Ricoh writes "GR II" with the maker only in Make; Canon writes
        # "Canon EOS 5D Mark II" with the maker in both. Show one or the other.
        if self.make and not model.lower().startswith(self.make.split()[0].lower()):
            model = f"{self.make.split()[0]} {model}"
        return f"{model} #{self.serial}" if self.serial else model

    @property
    def days(self):
        """{date: count}, in date order."""
        return dict(sorted(Counter(f.day for f in self.frames).items()))

    @property
    def extensions(self):
        return dict(sorted(Counter(f.path.suffix.upper() for f in self.frames).items()))

    @property
    def undated(self):
        """Frames whose date is only the file's mtime, so probably wrong."""
        return [f for f in self.frames if f.dated_from == "mtime"]

    @property
    def lenses(self):
        return dict(Counter(f.lens for f in self.frames if f.lens).most_common())

    @property
    def first(self):
        return min(f.captured for f in self.frames)

    @property
    def last(self):
        return max(f.captured for f in self.frames)


def image_files(roots):
    """Every image under the given folders, whatever camera it came from."""
    files = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        files.extend(
            p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXT
        )
    return sorted(set(files))


def group(frames):
    """Split frames by (make, model, serial), most frames first.

    Serial is part of the key on purpose: two 5D bodies are two cameras, and a
    folder that mixes them is exactly the kind that needs sorting.
    """
    groups = {}
    for frame in frames:
        key = (frame.make, frame.model, frame.serial)
        groups.setdefault(key, Group(*key)).frames.append(frame)
    return sorted(groups.values(), key=lambda g: (-len(g.frames), g.label))
