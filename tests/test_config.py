import pytest

from photoflow import config


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_defaults_load_without_a_config_file(tmp_path):
    cfg = config.load(tmp_path / "absent.toml", write_example=False)
    assert cfg.archive.name == "Archive"
    assert cfg.camera("grii").volume == "RICOH_GR"


def test_user_values_override_defaults_but_leave_the_rest(tmp_path):
    path = write(tmp_path, '[roots]\narchive = "~/NAS/originals"\n')
    cfg = config.load(path, write_example=False)
    assert cfg.archive.is_absolute() and cfg.archive.name == "originals"
    assert cfg.web.name == "Web"  # untouched default survives
    assert cfg.preset("web")["long_edge"] == 2560


def test_a_preset_can_be_tuned_without_restating_it(tmp_path):
    path = write(tmp_path, "[derive.web]\nlong_edge = 1600\n")
    cfg = config.load(path, write_example=False)
    assert cfg.preset("web")["long_edge"] == 1600
    assert cfg.preset("web")["quality"] == 90


def test_declaring_cameras_replaces_the_default_list(tmp_path):
    path = write(
        tmp_path,
        '[[cameras]]\nid = "x100"\nvolume = "FUJI"\n'
        'raw_ext = [".RAF"]\njpg_ext = [".JPG"]\n',
    )
    cfg = config.load(path, write_example=False)
    assert [c.id for c in cfg.cameras] == ["x100"]
    assert cfg.camera_by_volume("FUJI").id == "x100"


def test_extensions_are_matched_case_insensitively(tmp_path):
    from pathlib import Path

    cam = config.load(tmp_path / "absent.toml", write_example=False).camera("grii")
    assert cam.kind(Path("R0010948.DNG")) == "raw"
    assert cam.kind(Path("R0010948.jpg")) == "jpg"
    assert cam.kind(Path("RDSC.DB")) is None


def test_an_unknown_camera_or_preset_fails_loudly(tmp_path):
    cfg = config.load(tmp_path / "absent.toml", write_example=False)
    with pytest.raises(SystemExit):
        cfg.camera("nope")
    with pytest.raises(SystemExit):
        cfg.preset("nope")
