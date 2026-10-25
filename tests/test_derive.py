import os
import time

from photoflow import derive, imaging


def test_derivative_of_a_future_dated_original_is_not_rendered_twice(tmp_path, monkeypatch):
    # A card's FAT timestamps have no timezone, so a fresh frame can carry an
    # mtime ahead of the wall clock. It must still count as current once made.
    shoot = tmp_path / "2026-10-04"
    (shoot / "jpg").mkdir(parents=True)
    src = shoot / "jpg" / "20261004-145332_R0011087.JPG"
    src.write_bytes(b"original")
    ahead = time.time() + 3600
    os.utime(src, (ahead, ahead))

    rendered = []

    def convert(src, dest, **kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"derivative")
        rendered.append(dest)

    monkeypatch.setattr(imaging, "require_magick", lambda: None)
    monkeypatch.setattr(imaging, "convert", convert)

    for _ in range(2):
        derive.render(shoot, shoot / "thumb", {"long_edge": 400}, report=lambda line: None)
    assert len(rendered) == 1
