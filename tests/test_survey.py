from datetime import date

from conftest import frame
from photoflow import survey


def body(name, when, model="GR II", make="RICOH IMAGING COMPANY, LTD.", serial="", **kw):
    f = frame(name, when, **kw)
    f.make, f.model, f.serial = make, model, serial
    return f


def test_groups_by_body_and_counts_days():
    frames = [
        body("IMG_1.CR2", "2010-03-13T20:37:01", "Canon EOS 5D Mark II", "Canon", "111"),
        body("IMG_2.CR2", "2010-03-13T20:38:01", "Canon EOS 5D Mark II", "Canon", "111"),
        body("IMG_3.CR2", "2010-03-14T09:00:00", "Canon EOS 5D Mark II", "Canon", "111"),
        body("R0010001.DNG", "2016-01-01T12:00:00"),
    ]
    groups = survey.group(frames)
    assert [g.label for g in groups] == ["Canon EOS 5D Mark II #111", "RICOH GR II"]
    assert groups[0].days == {date(2010, 3, 13): 2, date(2010, 3, 14): 1}
    assert groups[0].extensions == {".CR2": 3}


def test_same_model_different_serial_is_two_cameras():
    frames = [
        body("a.CR2", "2010-03-13T20:37:01", "Canon EOS 5D Mark II", "Canon", "111"),
        body("b.CR2", "2010-03-13T20:37:01", "Canon EOS 5D Mark II", "Canon", "222"),
    ]
    assert len(survey.group(frames)) == 2


def test_undated_frames_are_flagged():
    frames = [
        body("a.JPG", "2010-03-13T20:37:01"),
        body("b.JPG", "2010-03-13T20:37:01", dated_from="mtime"),
    ]
    (g,) = survey.group(frames)
    assert [f.stem for f in g.undated] == ["b"]


def test_label_handles_missing_model():
    (g,) = survey.group([body("a.JPG", "2010-03-13T20:37:01", model="", make="")])
    assert g.label == "(no EXIF model)"
