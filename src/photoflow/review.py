"""Serve the day folders to the browser for triage, and record the decisions.

The review UI is a single-page app built from `web/` into `static/`. This
module is the thin server behind it: it lists the day folders under a root with
how far each has been reviewed, hands the SPA one day's frames with their
thumbnails, and writes each decision straight into `review.json` in that day
folder. That file is the working state while the day sits in the inbox; `push`
later turns it into XMP sidecars and archive folders.

Nothing here records which days exist or which are finished: the list is a walk
of the tree and "reviewed" is counted from review.json, so the tree still needs
no database.

Stdlib only on purpose: two clients and a few hundred files do not need a
framework, and the server must start instantly after an ingest.
"""

import json
import mimetypes
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import derive, meta, paths

REVIEW = "review.json"
STATIC = files("photoflow") / "static"

# Which derivative presets a review needs, and the subfolder each lands in.
DERIVATIVES = {"thumb": "thumb", "web": "web"}

# How many thumbnails the day list shows for each day.
COVERS = 6


class BadRequest(Exception):
    pass


def _dimensions(thumbs):
    """{path: (w, h)} for a batch of files, one exiftool call."""
    if not thumbs:
        return {}
    meta.require_exiftool()
    result = subprocess.run(
        ["exiftool", "-j", "-n", "-q", "-ImageWidth", "-ImageHeight", *map(str, thumbs)],
        capture_output=True,
        text=True,
    )
    out = {}
    for rec in json.loads(result.stdout or "[]"):
        out[Path(rec["SourceFile"])] = (rec.get("ImageWidth", 3), rec.get("ImageHeight", 2))
    return out


def _captured(stem):
    """`20260830-094759_R0010948` -> ISO timestamp, or None for a loose stem."""
    head = stem.split("_", 1)[0]
    if len(head) < 15 or head[8] != "-":
        return None
    d, t = head[:8], head[9:15]
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}T{t[:2]}:{t[2:4]}:{t[4:6]}"


def _clean_patch(patch):
    """Check a decision from the browser; anything unexpected is refused."""
    if not isinstance(patch, dict):
        raise BadRequest("patch must be an object")
    clean = {}
    for key, value in patch.items():
        if key in ("reject", "favourite", "keep"):
            ok = isinstance(value, bool)
        elif key == "rating":
            ok = isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 5
        elif key == "group":
            ok = isinstance(value, str) and len(value) <= 100
        else:
            raise BadRequest(f"unknown decision '{key}'")
        if not ok:
            raise BadRequest(f"bad value for '{key}'")
        clean[key] = value
    return clean


class Shoot:
    """One day folder: its frames, its derivatives, and its decisions."""

    def __init__(self, key, day, cfg, report=print):
        self.key = key
        self.day = Path(day).resolve()
        self.cfg = cfg
        self.report = report
        self.lock = threading.Lock()
        # Rendering is slow and both the background pass and a browser opening
        # the day may ask for it; the second one waits rather than racing.
        self.render_lock = threading.Lock()
        self.state = self._load()

    def _load(self):
        path = self.day / REVIEW
        state = {}
        if path.exists():
            try:
                state = json.loads(path.read_text())
                if not isinstance(state, dict):
                    raise ValueError("not an object")
            except ValueError:
                # Never start afresh over a file that may hold an evening of
                # decisions: move it aside where it can be repaired by hand.
                aside = path.with_name(f"{REVIEW}.unreadable-{datetime.now():%Y%m%d-%H%M%S}")
                path.rename(aside)
                self.report(f"{self.day.name}: {REVIEW} is not valid JSON; moved to {aside.name}")
                state = {}
        if not isinstance(state.get("groups"), list):
            state["groups"] = []
        if not isinstance(state.get("frames"), dict):
            state["frames"] = {}
        return state

    def _save(self):
        path = self.day / REVIEW
        tmp = path.with_suffix(".json.partial")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n")
        tmp.replace(path)

    def _url(self, kind, stem):
        return f"/img/{kind}/{quote(stem)}.jpg?day={quote(self.key, safe='')}"

    def stems(self):
        return sorted(derive.sources(self.day))

    def _ingested(self):
        """When the day was last ingested, for sorting the day list.

        The manifest says so exactly; without it the folder's own mtime is a
        fair stand-in, so the manifest stays an audit trail and nothing more.
        """
        try:
            return json.loads((self.day / paths.MANIFEST).read_text())["updated"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        newest = max(
            (p.stat().st_mtime for p in (self.day / "raw", self.day / "jpg", self.day) if p.exists())
        )
        return datetime.fromtimestamp(newest).isoformat(timespec="seconds")

    def summary(self):
        """What the day list shows: cheap, no subprocesses."""
        stems = self.stems()
        with self.lock:
            decisions = [self.state["frames"].get(s) for s in stems]
        have = [s for s in stems if (self.day / "thumb" / f"{s}.jpg").is_file()]
        step = max(1, len(have) // COVERS)
        date = paths.shoot_day(self.day)
        return {
            "key": self.key,
            "name": self.day.name,
            "path": str(self.day),
            "date": date.isoformat() if date else None,
            "ingested": self._ingested(),
            "total": len(stems),
            "decided": sum(1 for d in decisions if d),
            "rejected": sum(1 for d in decisions if d and d.get("reject")),
            "rendered": len(have),
            "covers": [self._url("thumb", s) for s in have[::step][:COVERS]],
        }

    def render(self):
        """Make sure `day/thumb` and `day/web` exist and are current."""
        with self.render_lock:
            for preset, sub in DERIVATIVES.items():
                derive.render(
                    self.day,
                    self.day / sub,
                    self.cfg.preset(preset),
                    jobs=os.cpu_count() or 4,
                    report=self.report,
                )

    def payload(self):
        self.render()
        # The frames are the originals, not the thumbnails: a frame whose
        # render failed must still be listed, or it could never be decided on.
        stems = self.stems()
        thumbs = {s: self.day / "thumb" / f"{s}.jpg" for s in stems}
        dims = _dimensions([t for t in thumbs.values() if t.is_file()])
        raws = {p.stem for p in (self.day / "raw").glob("*")}
        with self.lock:
            frames = []
            for stem in stems:
                w, h = dims.get(thumbs[stem], (3, 2))
                frames.append(
                    {
                        "id": stem,
                        "thumb": self._url("thumb", stem),
                        "web": self._url("web", stem),
                        "width": w,
                        "height": h,
                        "captured": _captured(stem),
                        "raw": stem in raws,
                        **self.state["frames"].get(stem, {}),
                    }
                )
            return {
                "key": self.key,
                "name": self.day.name,
                "path": str(self.day),
                "groups": list(self.state["groups"]),
                "frames": frames,
            }

    def decide(self, ids, patch):
        """Apply the same decision to several frames, e.g. a multi-select."""
        patch = _clean_patch(patch)
        known = set(self.stems())
        if not isinstance(ids, list) or not all(isinstance(i, str) and i in known for i in ids):
            raise BadRequest("unknown frame id")
        with self.lock:
            for fid in ids:
                current = self.state["frames"].setdefault(fid, {})
                current.update(patch)
                # Drop keys back to "undecided" so the file stays readable.
                for k in list(current):
                    if current[k] in (None, False, 0, ""):
                        del current[k]
                if not current:
                    del self.state["frames"][fid]
            if patch.get("group") and patch["group"] not in self.state["groups"]:
                self.state["groups"].append(patch["group"])
            self._save()

    def set_groups(self, groups):
        if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
            raise BadRequest("groups must be a list of names")
        with self.lock:
            self.state["groups"] = [g for g in groups if g]
            self._save()


class Library:
    """Every day folder under the root, found by walking it."""

    def __init__(self, root, cfg, report=print):
        self.root = Path(root).expanduser().resolve()
        self.cfg = cfg
        self.report = report
        self.lock = threading.Lock()
        self.shoots = {}
        self.refresh()

    def refresh(self):
        """Pick up days ingested since the server started."""
        found = derive.shoot_dirs([self.root], self.root) if self.root.is_dir() else []
        with self.lock:
            for day in found:
                key = day.relative_to(self.root).as_posix()
                if key not in self.shoots:
                    self.shoots[key] = Shoot(key, day, self.cfg, self.report)

    def add(self, day):
        """A folder named on the command line, wherever it lives."""
        day = Path(day).resolve()
        try:
            key = day.relative_to(self.root).as_posix()
        except ValueError:
            key = day.name
        with self.lock:
            if key not in self.shoots:
                self.shoots[key] = Shoot(key, day, self.cfg, self.report)
        return key

    def get(self, key):
        with self.lock:
            return self.shoots.get(key)

    def all(self):
        with self.lock:
            return list(self.shoots.values())

    def resolve(self, target):
        """Turn `review <target>` into a day key: a path, or a date or name."""
        path = Path(target).expanduser()
        if path.is_dir():
            if not derive.sources(path):
                sys.exit(f"no images in {path.resolve()}")
            return self.add(path)
        matches = [s.key for s in self.all() if s.day.name.startswith(target)]
        if len(matches) == 1:
            return matches[0]
        if matches:
            sys.exit(f"'{target}' matches several days:\n  " + "\n  ".join(sorted(matches)))
        known = "\n  ".join(sorted(s.key for s in self.all())) or "(none)"
        sys.exit(f"no folder or day matches '{target}'. Days under {self.root}:\n  {known}")

    def render_all(self):
        """Background pass, newest first, so the day list fills with covers."""
        for shoot in sorted(self.all(), key=lambda s: s.day.name, reverse=True):
            try:
                shoot.render()
            except Exception as exc:  # one bad day must not stop the rest
                self.report(f"{shoot.day.name}: render failed: {exc}")


class Handler(SimpleHTTPRequestHandler):
    # HTTP/1.0 (the default) closes the socket after every response, which
    # turns a grid of two hundred thumbnails into two hundred connections.
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, library, **kwargs):
        self.library = library
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        pass

    # -- responses ---------------------------------------------------------

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, cache):
        if not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 16):
                self.wfile.write(chunk)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            raise BadRequest("body is not JSON") from None
        if not isinstance(body, dict):
            raise BadRequest("body must be an object")
        return body

    def _shoot(self, key):
        shoot = self.library.get(key) if isinstance(key, str) else None
        if shoot is None:
            raise BadRequest("unknown day")
        return shoot

    def _same_origin(self):
        """Refuse writes sent by some other web page open in the browser."""
        origin = self.headers.get("Origin")
        return origin is None or urlsplit(origin).netloc == self.headers.get("Host")

    # -- routes ------------------------------------------------------------

    def do_GET(self):
        url = urlsplit(self.path)
        route = url.path
        day = parse_qs(url.query).get("day", [None])[0]
        try:
            if route == "/api/days":
                self.library.refresh()
                return self._json(
                    {
                        "root": str(self.library.root),
                        "done_at": self.library.cfg.review.get("done_at", 0.8),
                        "days": [s.summary() for s in self.library.all()],
                    }
                )
            if route == "/api/shoot":
                return self._json(self._shoot(day).payload())
            if route.startswith("/img/"):
                parts = route.split("/")
                if len(parts) != 4 or parts[2] not in DERIVATIVES.values():
                    return self.send_error(404)
                # Decode first, then check: an encoded slash must not get a
                # name past the test and out of the day folder.
                name = unquote(parts[3])
                if not name or name != Path(name).name:
                    return self.send_error(404)
                # Derivative names are stable for a given original, so the
                # browser may keep them for the session.
                return self._file(self._shoot(day).day / parts[2] / name, "max-age=86400")
        except BadRequest as exc:
            return self._json({"error": str(exc)}, 400)
        # Anything else is the SPA; unknown paths fall back to index.html.
        if not (STATIC / route.lstrip("/")).is_file():
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        route = urlsplit(self.path).path
        if not self._same_origin():
            return self._json({"error": "cross-origin request refused"}, 403)
        try:
            body = self._body()
            if route == "/api/decide":
                self._shoot(body.get("day")).decide(body.get("ids", []), body.get("patch", {}))
                return self._json({"ok": True})
            if route == "/api/groups":
                self._shoot(body.get("day")).set_groups(body.get("groups", []))
                return self._json({"ok": True})
        except BadRequest as exc:
            return self._json({"error": str(exc)}, 400)
        self.send_error(404)


def _lan_address():
    """This machine's address on the LAN, for the URL a tablet should use."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packet is sent; connecting a UDP socket only picks the interface.
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        probe.close()


def serve(target, cfg, host="127.0.0.1", port=8765, open_browser=True, report=print):
    if not (STATIC / "index.html").is_file():
        sys.exit("review UI not built — run `npm run build` in web/ first")

    library = Library(cfg.archive, cfg, report)
    key = library.resolve(target) if target else None
    if not library.all():
        sys.exit(f"nothing to review under {library.root} — run `photoflow ingest` first")

    try:
        server = ThreadingHTTPServer((host, port), partial(Handler, library=library))
    except OSError as exc:
        sys.exit(f"cannot listen on port {port} ({exc.strerror}) — is another review running? Try --port")

    # One magick per core, each single-threaded, beats one magick using all
    # cores: the per-process start and decode dominate at these sizes.
    os.environ.setdefault("MAGICK_THREAD_LIMIT", "1")
    threading.Thread(target=library.render_all, daemon=True).start()

    local = f"http://localhost:{port}/"
    report(f"{len(library.all())} day(s) under {library.root} at {local}  (Ctrl-C to stop)")
    if host != "127.0.0.1":
        report(f"on the LAN: http://{_lan_address()}:{port}/")
    if open_browser:
        # Give the server a moment to be listening before the tab asks.
        threading.Timer(0.3, webbrowser.open, [local + (f"?day={quote(key, safe='')}" if key else "")]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
