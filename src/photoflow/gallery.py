"""Generate self-contained static contact sheets.

No CDN, no build step, no server: inline CSS and a few dozen lines of JS, so a
gallery works opened straight off disk with file:// and works just as well from
a NAS share or a phone. The point is to triage a card in a browser without
importing anything anywhere.
"""

import html
import json
from datetime import datetime
from pathlib import Path

from . import derive, paths

PAGE = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #faf9f7; --fg: #1b1b1b; --dim: #6b6b6b; --line: #e0ded9; --card: #fff;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #131313; --fg: #e8e6e3; --dim: #9a9a9a; --line: #2b2b2b; --card: #1c1c1c; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg);
         font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  header { padding: 1.5rem clamp(1rem, 4vw, 3rem) 1rem; border-bottom: 1px solid var(--line); }
  h1 { margin: 0 0 .25rem; font-size: 1.4rem; font-weight: 600; letter-spacing: -.01em; }
  .meta { color: var(--dim); font-size: .875rem; }
  .meta a { color: inherit; }
  main { padding: clamp(1rem, 4vw, 3rem); }
  .grid { display: grid; gap: 14px;
          grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }
  figure { margin: 0; background: var(--card); border: 1px solid var(--line);
           border-radius: 6px; overflow: hidden; cursor: zoom-in; }
  figure img { display: block; width: 100%; aspect-ratio: 3/2; object-fit: cover;
               background: var(--line); }
  figcaption { padding: .45rem .6rem; font-size: .75rem; color: var(--dim);
               display: flex; justify-content: space-between; gap: .5rem; }
  .raw { border: 1px solid var(--line); border-radius: 3px; padding: 0 .3rem;
         font-size: .68rem; letter-spacing: .04em; }
  .links { display: grid; gap: .5rem; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); }
  .links a { display: block; padding: .8rem 1rem; background: var(--card);
             border: 1px solid var(--line); border-radius: 6px;
             color: inherit; text-decoration: none; }
  .links a:hover { border-color: var(--dim); }
  .links span { display: block; color: var(--dim); font-size: .8rem; }
  #lb { position: fixed; inset: 0; background: rgba(0,0,0,.94); display: none;
        align-items: center; justify-content: center; z-index: 9; }
  #lb.on { display: flex; }
  #lb img { max-width: 96vw; max-height: 88vh; object-fit: contain; }
  #lb .bar { position: fixed; bottom: 0; left: 0; right: 0; padding: .8rem 1rem;
             color: #ddd; font-size: .8rem; text-align: center;
             background: linear-gradient(transparent, rgba(0,0,0,.7)); }
  #lb button { position: fixed; top: 50%; transform: translateY(-50%);
               background: none; border: 0; color: #fff; font-size: 2.4rem;
               cursor: pointer; padding: 0 1rem; opacity: .6; }
  #lb button:hover { opacity: 1; }
  #prev { left: 0; } #next { right: 0; } #shut { top: 0; right: 0; transform: none; font-size: 1.8rem; }
</style>
<header>
  <h1>__HEADING__</h1>
  <div class="meta">__SUBTITLE__</div>
</header>
<main>__BODY__</main>
<div id="lb">
  <button id="prev" aria-label="Previous">&#8249;</button>
  <img alt="">
  <button id="next" aria-label="Next">&#8250;</button>
  <button id="shut" aria-label="Close">&times;</button>
  <div class="bar"></div>
</div>
<script>
const SHOTS = __DATA__;
const lb = document.getElementById('lb'), img = lb.querySelector('img'),
      bar = lb.querySelector('.bar');
let at = 0;
function show(i) {
  if (!SHOTS.length) return;
  at = (i + SHOTS.length) % SHOTS.length;
  const s = SHOTS[at];
  img.src = s.full; img.alt = s.name;
  bar.textContent = `${at + 1} / ${SHOTS.length}  ·  ${s.name}` + (s.time ? `  ·  ${s.time}` : '');
  lb.classList.add('on');
}
function hide() { lb.classList.remove('on'); img.src = ''; }
document.querySelectorAll('figure').forEach((f, i) => f.onclick = () => show(i));
document.getElementById('prev').onclick = e => { e.stopPropagation(); show(at - 1); };
document.getElementById('next').onclick = e => { e.stopPropagation(); show(at + 1); };
document.getElementById('shut').onclick = e => { e.stopPropagation(); hide(); };
lb.onclick = e => { if (e.target === lb || e.target === img) hide(); };
addEventListener('keydown', e => {
  if (!lb.classList.contains('on')) return;
  if (e.key === 'Escape') hide();
  else if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); show(at + 1); }
  else if (e.key === 'ArrowLeft') show(at - 1);
});
</script>
"""


def _page(title, heading, subtitle, body, data):
    return (
        PAGE.replace("__TITLE__", html.escape(title))
        .replace("__HEADING__", html.escape(heading))
        .replace("__SUBTITLE__", subtitle)
        .replace("__BODY__", body)
        .replace("__DATA__", json.dumps(data))
    )


def _captured(shoot, stem):
    """Capture time from the ingest manifest, when there is one."""
    manifest = shoot / paths.MANIFEST
    if not manifest.exists():
        return {}
    try:
        records = json.loads(manifest.read_text()).get("files", [])
    except (OSError, json.JSONDecodeError):
        return {}
    return {Path(r["dest"]).stem: r.get("captured", "") for r in records}


def build_shoot(shoot, dest, cfg, prefer="auto", jobs=4, force=False, report=print):
    """Render full-size and thumbnail derivatives, then an index.html over them."""
    from . import derive as _derive

    originals = _derive.sources(shoot, prefer)
    if not originals:
        report(f"{shoot}: no images")
        return None

    _derive.render(shoot, dest, cfg.preset("web"), prefer, None, jobs, force, report)
    _derive.render(shoot, dest, cfg.preset("thumb"), prefer, "thumbs", jobs, force, report)

    has_raw = {p.stem for p in (shoot / "raw").glob("*")}
    times = _captured(shoot, None)

    cards, data = [], []
    for stem in sorted(originals):
        time = times.get(stem, "")
        pretty = time.replace("T", " ")[11:16] if time else ""
        raw = '<span class="raw">RAW</span>' if stem in has_raw else ""
        cards.append(
            f'<figure><img loading="lazy" src="thumbs/{html.escape(stem)}.jpg" '
            f'alt="{html.escape(stem)}"><figcaption>'
            f"<span>{html.escape(pretty)}</span>{raw}</figcaption></figure>"
        )
        data.append({"full": f"{stem}.jpg", "name": stem, "time": pretty})

    day = paths.shoot_day(shoot)
    subtitle = f"{len(data)} photograph{'s' if len(data) != 1 else ''}"
    if day:
        subtitle = f"{day.strftime('%A %-d %B %Y')} · {subtitle}"

    dest.mkdir(parents=True, exist_ok=True)
    page = _page(shoot.name, shoot.name, subtitle, f'<div class="grid">{"".join(cards)}</div>', data)
    (dest / "index.html").write_text(page)
    report(f"  index.html -> {dest / 'index.html'}")
    return dest


def build_index(root, report=print):
    """Write index.html pages over every directory that contains galleries.

    Walks bottom-up so a year page can count the shoots beneath it, and the top
    of the web tree ends up browsable in a browser with no server.
    """
    root = Path(root)
    written = []
    for directory in sorted(root.rglob("*"), reverse=True) + [root]:
        if not directory.is_dir() or directory.name == "thumbs":
            continue
        children = [
            d
            for d in sorted(directory.iterdir())
            if d.is_dir() and d.name != "thumbs" and (d / "index.html").exists()
        ]
        if not children or (directory / "thumbs").is_dir():
            continue
        links = []
        for child in children:
            count = len(list((child / "thumbs").glob("*.jpg"))) if (child / "thumbs").is_dir() else 0
            note = f"{count} photograph{'s' if count != 1 else ''}" if count else "browse"
            links.append(
                f'<a href="{html.escape(child.name)}/index.html">'
                f"{html.escape(child.name)}<span>{note}</span></a>"
            )
        title = directory.name if directory != root else "Photographs"
        page = _page(title, title, f"{len(children)} folder(s)", f'<div class="links">{"".join(links)}</div>', [])
        (directory / "index.html").write_text(page)
        written.append(directory / "index.html")
    for path in written:
        report(f"  index -> {path}")
    return written
