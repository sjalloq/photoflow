import json

from photoflow import purge


def day_with(tmp_path, stems, state):
    day = tmp_path / "2026-10-04"
    for stem in stems:
        for part, ext in (("raw", ".DNG"), ("jpg", ".JPG"), ("thumb", ".jpg"), ("web", ".jpg")):
            (day / part).mkdir(parents=True, exist_ok=True)
            (day / part / f"{stem}{ext}").write_bytes(b"x")
    (day / "review.json").write_text(json.dumps(state))
    return day


def test_rejected_stems_lose_every_part_and_nothing_else(tmp_path):
    keep, dud, clash = "20261004-1_R0010948", "20261004-2_R0010949", "20261004-2_R0010949-2"
    day = day_with(
        tmp_path,
        [keep, dud, clash],
        {"groups": [], "frames": {dud: {"reject": True}, keep: {"keep": True}, clash: {"rating": 3}}},
    )

    stems = purge.rejected(purge.load_state(day))
    assert stems == [dud]
    files = purge.victims(day, stems)
    # The DNG and JPEG are one photograph, and the derivatives go with them.
    assert sorted(p.relative_to(day).as_posix() for p in files) == [
        f"jpg/{dud}.JPG", f"raw/{dud}.DNG", f"thumb/{dud}.jpg", f"web/{dud}.jpg",
    ]

    assert purge.run([day], assume_yes=True, report=lambda line: None) == 0
    survivors = sorted(p.name for p in day.rglob("*") if p.is_file() and p.name != "review.json")
    assert dud not in {p.rsplit(".", 1)[0] for p in survivors}
    # A -2 suffix is a different photograph that clashed on its name; the exact
    # stem match must leave it alone.
    assert f"{clash}.DNG" in survivors and f"{keep}.JPG" in survivors

    state = json.loads((day / "review.json").read_text())
    assert dud not in state["frames"]
    assert state["frames"][keep] == {"keep": True}
    assert [p["id"] for p in state["purged"]] == [dud]


def test_dry_run_deletes_nothing(tmp_path):
    dud = "20261004-2_R0010949"
    day = day_with(tmp_path, [dud], {"groups": [], "frames": {dud: {"reject": True}}})
    assert purge.run([day], dry_run=True, report=lambda line: None) == 0
    assert (day / "raw" / f"{dud}.DNG").exists()
    assert "purged" not in json.loads((day / "review.json").read_text())


def test_day_without_review_or_rejects_is_untouched(tmp_path):
    day = day_with(tmp_path, ["20261004-1_R0010948"], {"groups": [], "frames": {}})
    (day / "review.json").unlink()
    assert purge.rejected(purge.load_state(day)) == []
    assert purge.run([day], assume_yes=True, report=lambda line: None) == 0
    assert not (day / "review.json").exists()
