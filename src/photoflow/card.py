"""Find the camera's SD card, mounting it if the desktop hasn't already."""

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _lsblk():
    if not shutil.which("lsblk"):
        return []
    out = subprocess.run(
        ["lsblk", "-J", "-o", "PATH,LABEL,FSTYPE,MOUNTPOINT"],
        capture_output=True,
        text=True,
    ).stdout
    devices = []

    def walk(nodes):
        for node in nodes:
            devices.append(node)
            walk(node.get("children", []))

    try:
        walk(json.loads(out).get("blockdevices", []))
    except json.JSONDecodeError:
        return []
    return devices


class Card:
    """A mounted card, and whether we are the ones who mounted it."""

    def __init__(self, path, camera, device=None, mounted_by_us=False):
        self.path = Path(path)
        self.camera = camera
        self.device = device
        self.mounted_by_us = mounted_by_us

    def files(self):
        """Every file on the card matching the camera's extensions."""
        root = self.path / "DCIM"
        if not root.is_dir():
            root = self.path
        return sorted(
            p
            for p in root.rglob("*")
            if p.is_file() and self.camera.kind(p) is not None
        )

    def release(self):
        """Unmount, but only if we mounted it — never yank it out from under
        a file manager the user opened themselves."""
        if not self.mounted_by_us or not self.device:
            return
        subprocess.run(
            ["udisksctl", "unmount", "-b", self.device],
            capture_output=True,
            text=True,
        )


def _mount(device):
    if not shutil.which("udisksctl"):
        sys.exit(f"{device} is not mounted and udisksctl is unavailable")
    result = subprocess.run(
        ["udisksctl", "mount", "-b", device], capture_output=True, text=True
    )
    if result.returncode != 0:
        sys.exit(f"could not mount {device}: {result.stderr.strip()}")
    # "Mounted /dev/sda1 at /run/media/user/RICOH_GR"
    for token in ("at ",):
        _, _, tail = result.stdout.strip().partition(token)
        if tail:
            return Path(tail.rstrip("."))
    sys.exit(f"could not parse mount point from: {result.stdout.strip()}")


def find(cfg, path=None, camera_id=None):
    """Locate the card: an explicit path, else a volume matching a profile."""
    if path:
        path = Path(path).expanduser()
        if not path.is_dir():
            sys.exit(f"no such directory: {path}")
        camera = cfg.camera(camera_id) if camera_id else cfg.cameras[0]
        return Card(path, camera)

    wanted = [cfg.camera(camera_id)] if camera_id else cfg.cameras
    devices = _lsblk()

    for camera in wanted:
        if not camera.volume:
            continue
        for device in devices:
            if device.get("label") != camera.volume:
                continue
            if device.get("mountpoint"):
                return Card(device["mountpoint"], camera, device["path"])
            mount = _mount(device["path"])
            return Card(mount, camera, device["path"], mounted_by_us=True)

    names = ", ".join(c.volume for c in wanted if c.volume) or "(none configured)"
    sys.exit(
        f"no camera card found — looked for a volume labelled {names}.\n"
        "Insert the card, or pass --card with the path to the files."
    )
