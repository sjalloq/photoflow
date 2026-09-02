from datetime import date
from pathlib import Path

import pytest
from conftest import frame

from photoflow import paths
from photoflow.config import Camera

CAMERA = Camera(
    {"id": "grii", "volume": "RICOH_GR", "raw_ext": [".dng"], "jpg_ext": [".jpg"]}
)


@pytest.fixture
def archive(tmp_path):
    return tmp_path / "Archive"


def plan(frames, archive, name=None):
    return paths.plan_shoots(frames, CAMERA, archive, name)


def test_slugify_folds_free_text_into_a_folder_name():
    assert paths.slugify("Brighton Beach") == "brighton-beach"
    assert paths.slugify("  Dad's 60th!  ") == "dad-s-60th"


def test_raw_and_jpeg_of_one_frame_share_a_stem(archive):
    shoots = plan(
        [frame("R0010948.DNG", "2026-08-30 09:47:59"),
         frame("R0010948.JPG", "2026-08-30 09:47:59")],
        archive,
    )
    assert len(shoots) == 1
    stems = {p.dest.stem for p in shoots[0].plans}
    assert stems == {"20260830-094759_R0010948"}
    kinds = {p.kind: p.dest for p in shoots[0].plans}
    assert kinds["raw"].parent.name == "raw"
    assert kinds["jpg"].parent.name == "jpg"


def test_the_raw_timestamp_wins_when_the_jpeg_disagrees(archive):
    # The JPEG is written a moment after the RAW; both must file under the RAW.
    shoots = plan(
        [frame("R0010948.DNG", "2026-08-30 09:47:59"),
         frame("R0010948.JPG", "2026-08-30 09:48:02")],
        archive,
    )
    assert {p.dest.stem for p in shoots[0].plans} == {"20260830-094759_R0010948"}


def test_frames_split_into_one_shoot_per_capture_day(archive):
    shoots = plan(
        [frame("R0010948.DNG", "2026-08-30 09:47:59"),
         frame("R0011002.DNG", "2026-08-31 11:12:57")],
        archive,
    )
    assert [s.day for s in shoots] == [date(2026, 8, 30), date(2026, 8, 31)]
    assert shoots[0].directory == archive / "grii/2026/2026-08-30"


def test_a_name_becomes_a_folder_suffix(archive):
    shoots = plan([frame("R0010948.DNG", "2026-08-30 09:47:59")], archive, "Brighton Beach")
    assert shoots[0].directory.name == "2026-08-30_brighton-beach"


def test_a_later_run_joins_the_day_already_on_disk(archive):
    existing = archive / "grii/2026/2026-08-30_brighton-beach"
    existing.mkdir(parents=True)
    # A different --name must not fork the day into a second folder.
    shoots = plan([frame("R0010948.DNG", "2026-08-30 09:47:59")], archive, "somewhere else")
    assert shoots[0].directory == existing


def test_a_repeated_camera_stem_is_suffixed_not_shadowed(archive):
    # The GR II's counter wraps, so two DCIM folders can hold the same name.
    a = frame("R0010948.DNG", "2026-08-30 09:47:59")
    b = frame("R0010948.DNG", "2026-08-30 09:47:59")
    b.path = Path("/card/DCIM/101RICOH/R0010948.DNG")
    shoots = paths.plan_shoots([a, b], CAMERA, archive)
    stems = sorted(p.dest.stem for p in shoots[0].plans)
    assert stems == ["20260830-094759_R0010948", "20260830-094759_R0010948-2"]


def test_subsecond_precision_is_used_when_the_camera_records_it(archive):
    shoots = plan([frame("R0010948.DNG", "2026-08-30 09:47:59", subsec="42")], archive)
    assert shoots[0].plans[0].dest.stem == "20260830-094759.42_R0010948"


def test_files_the_camera_profile_does_not_claim_are_ignored(archive):
    shoots = plan(
        [frame("RDSC.DB", "2026-08-30 09:47:59"),
         frame("R0010948.DNG", "2026-08-30 09:47:59")],
        archive,
    )
    assert len(shoots[0].plans) == 1


def test_shoot_day_reads_the_date_back_out_of_the_folder_name():
    assert paths.shoot_day(Path("/a/2026-08-30_brighton-beach")) == date(2026, 8, 30)
    assert paths.shoot_day(Path("/a/2026-08-30")) == date(2026, 8, 30)
    assert paths.shoot_day(Path("/a/not-a-shoot")) is None
