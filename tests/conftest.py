import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from photoflow.meta import Frame  # noqa: E402


def frame(name, when, subsec="", dated_from="exif"):
    """A Frame standing in for a file on a card, without needing a real one."""
    return Frame(
        path=Path("/card/DCIM/100RICOH") / name,
        captured=datetime.fromisoformat(when),
        subsec=subsec,
        make="RICOH IMAGING COMPANY, LTD.",
        model="GR II",
        dated_from=dated_from,
    )
