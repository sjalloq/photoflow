"""Load ~/.config/photoflow/config.toml, falling back to built-in defaults.

The config exists so that the archive layout, the camera profiles and the derive
presets are data rather than code: a second camera, or a NAS path that doesn't
exist yet, should be a config edit and not a patch.
"""

import os
import tomllib
from pathlib import Path

CONFIG_PATH = Path(
    os.environ.get("PHOTOFLOW_CONFIG")
    or Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    / "photoflow"
    / "config.toml"
).expanduser()

DEFAULTS = {
    "roots": {
        "archive": "~/Pictures/Archive",
        "web": "~/Pictures/Web",
    },
    "sync": {
        "archive_target": "",
        "web_target": "",
    },
    "cameras": [
        {
            "id": "grii",
            "label": "Ricoh GR II",
            "volume": "RICOH_GR",
            "model": "GR II",
            "raw_ext": [".dng"],
            "jpg_ext": [".jpg"],
        }
    ],
    "derive": {
        "web": {"long_edge": 2560, "quality": 90, "sharpen": "medium"},
        "frame": {"long_edge": 1920, "quality": 88, "sharpen": "light"},
        "thumb": {"long_edge": 400, "quality": 80, "sharpen": "light"},
    },
}

EXAMPLE = '''# photoflow configuration.
# Written automatically on first run; edit freely, it is never rewritten.

[roots]
archive = "~/Pictures/Archive"   # originals, untouched
web     = "~/Pictures/Web"       # derived JPEGs and galleries

[sync]
# rsync destinations; empty means "not configured yet".
archive_target = ""              # e.g. "nas:/volume1/photo/archive"
web_target     = ""              # e.g. "nas:/volume1/photo/web"

[[cameras]]
id      = "grii"                 # becomes the top-level archive folder
label   = "Ricoh GR II"
volume  = "RICOH_GR"             # SD card filesystem label, for auto-detect
model   = "GR II"                 # EXIF Model, for attributing loose files
raw_ext = [".dng"]
jpg_ext = [".jpg"]

[derive.web]
long_edge = 2560
quality   = 90
sharpen   = "medium"

[derive.frame]
long_edge = 1920
quality   = 88
sharpen   = "light"

[derive.thumb]
long_edge = 400
quality   = 80
sharpen   = "light"
'''


class Camera:
    def __init__(self, d):
        self.id = d["id"]
        self.label = d.get("label", d["id"])
        self.volume = d.get("volume", "")
        self.model = d.get("model", "")
        self.raw_ext = {e.lower() for e in d.get("raw_ext", [])}
        self.jpg_ext = {e.lower() for e in d.get("jpg_ext", [])}

    @property
    def extensions(self):
        return self.raw_ext | self.jpg_ext

    def kind(self, path):
        """'raw', 'jpg' or None — which subdirectory a file belongs in."""
        ext = path.suffix.lower()
        if ext in self.raw_ext:
            return "raw"
        if ext in self.jpg_ext:
            return "jpg"
        return None

    def __repr__(self):
        return f"<Camera {self.id}>"


class Config:
    def __init__(self, data):
        self._data = data
        self.archive = Path(data["roots"]["archive"]).expanduser()
        self.web = Path(data["roots"]["web"]).expanduser()
        self.sync = data["sync"]
        self.cameras = [Camera(c) for c in data["cameras"]]
        self.presets = data["derive"]

    def camera(self, camera_id):
        for cam in self.cameras:
            if cam.id == camera_id:
                return cam
        known = ", ".join(c.id for c in self.cameras)
        raise SystemExit(f"unknown camera '{camera_id}' (configured: {known})")

    def camera_by_volume(self, label):
        for cam in self.cameras:
            if cam.volume and cam.volume == label:
                return cam
        return None

    def camera_by_model(self, model):
        for cam in self.cameras:
            if cam.model and cam.model == model:
                return cam
        return None

    def preset(self, name):
        if name not in self.presets:
            known = ", ".join(self.presets)
            raise SystemExit(f"unknown preset '{name}' (configured: {known})")
        return self.presets[name]


def _merge(base, overlay):
    """Recursive dict merge; lists and scalars in the overlay win outright."""
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def ensure_example(path=CONFIG_PATH):
    """Write a starter config on first run, so there's something to edit."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(EXAMPLE)
    return True


def load(path=None, write_example=True):
    path = Path(path).expanduser() if path else CONFIG_PATH
    if write_example and path == CONFIG_PATH and ensure_example(path):
        print(f"wrote a starter config to {path}")
    data = DEFAULTS
    if path.exists():
        with open(path, "rb") as fh:
            data = _merge(DEFAULTS, tomllib.load(fh))
    return Config(data)
