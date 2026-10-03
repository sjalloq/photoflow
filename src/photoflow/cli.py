"""Command-line entry point: photoflow <ingest|derive|gallery|sync|status|inspect|review>."""

import argparse
import sys
from pathlib import Path

from . import __version__, card, config, derive, gallery, ingest, meta, paths, review, survey, sync


def cmd_status(args, cfg):
    found = card.find(cfg, args.card, args.camera)
    try:
        files = found.files()
        print(f"{found.camera.label} at {found.path}")
        if not files:
            print("  no images found")
            return 0
        frames = meta.read(files)
        shoots = paths.plan_shoots(frames, found.camera, args.dest or cfg.archive)
        total_new = 0
        for shoot in shoots:
            ingest.classify(shoot.plans)
            new = len(shoot.new)
            total_new += new
            state = "all present" if not new else f"{new} not yet imported"
            print(f"  {shoot.day}  {len(shoot.plans):4d} file(s)  {state}")
            print(f"           -> {shoot.directory}")
        print(f"\n{len(files)} file(s) on the card, {total_new} not yet in the archive.")
        if total_new == 0:
            print("Everything here is archived — safe to format the card in-camera.")
        return 0
    finally:
        found.release()


def cmd_ingest(args, cfg):
    found = card.find(cfg, args.card, args.camera)
    try:
        archive = Path(args.dest).expanduser() if args.dest else cfg.archive
        ingest.run(found, archive, args.name, args.dry_run)
        return 0
    finally:
        found.release()


def _targets(args, cfg):
    roots = args.paths or [cfg.archive]
    shoots = derive.shoot_dirs(roots, cfg.archive)
    if not shoots:
        sys.exit("no shoot folders with images found")
    return shoots


def cmd_derive(args, cfg):
    preset = cfg.preset(args.preset)
    for shoot in _targets(args, cfg):
        dest = derive.out_dir(shoot, cfg.archive, cfg.web, args.out)
        derive.render(shoot, dest, preset, args.source, args.subdir, args.jobs, args.force)
    return 0


def cmd_gallery(args, cfg):
    roots = set()
    for shoot in _targets(args, cfg):
        dest = derive.out_dir(shoot, cfg.archive, cfg.web, args.out)
        gallery.build_shoot(shoot, dest, cfg, args.source, args.jobs, args.force)
        roots.add(Path(args.out).expanduser() if args.out else cfg.web)
    if not args.no_index:
        for root in roots:
            gallery.build_index(root)
    return 0


def cmd_inspect(args, cfg):
    roots = [Path(p).expanduser() for p in args.paths]
    for root in roots:
        if not root.exists():
            sys.exit(f"no such path: {root}")
    files = survey.image_files(roots)
    if not files:
        print("no image files found")
        return 0
    frames = meta.read(files)
    archive = Path(args.dest).expanduser() if args.dest else cfg.archive

    for g in survey.group(frames):
        exts = ", ".join(f"{n} {e}" for e, n in g.extensions.items())
        print(f"{g.label}: {len(g.frames)} file(s) ({exts})")
        print(f"  {g.first:%Y-%m-%d %H:%M} .. {g.last:%Y-%m-%d %H:%M}")
        if g.lenses:
            print("  lens: " + ", ".join(f"{lens} x{n}" for lens, n in g.lenses.items()))
        if g.undated:
            print(f"  {len(g.undated)} file(s) have no EXIF date; dated by file mtime, do not trust")
        camera = cfg.camera_by_model(g.model)
        if camera:
            print(f"  matches camera '{camera.id}' in the config")
        elif g.model:
            print(f'  no [[cameras]] profile has model = "{g.model}"')
        for day, n in g.days.items():
            line = f"  {day}  {n:4d} file(s)"
            if camera:
                line += f"  -> {paths.shoot_dir(archive, camera.id, day)}"
            print(line)
        if args.files:
            for f in sorted(g.frames, key=lambda f: (f.captured, f.path)):
                flag = "" if f.dated_from == "exif" else f"  [{f.dated_from}]"
                print(f"    {f.captured:%Y-%m-%d %H:%M:%S}  {f.path}{flag}")
        print()

    skipped = len(files) - len(frames)
    print(f"{len(frames)} file(s) read" + (f", {skipped} unreadable by exiftool" if skipped else ""))
    return 0


def cmd_review(args, cfg):
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    review.serve(args.target, cfg, host=host, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_sync(args, cfg):
    return sync.run(cfg, args.which, args.dry_run, args.delete)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="photoflow", description=__doc__.splitlines()[0]
    )
    p.add_argument("--version", action="version", version=f"photoflow {__version__}")
    p.add_argument("--config", help="path to config.toml")
    sub = p.add_subparsers(dest="command", required=True)

    def card_args(sp):
        sp.add_argument("--card", help="path to the card or a folder of originals")
        sp.add_argument("--camera", help="camera id from the config (default: auto-detect)")
        sp.add_argument("--dest", help="archive root for this run (default: from config)")

    sp = sub.add_parser("status", help="what is on the card and what is already archived")
    card_args(sp)
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("ingest", help="copy originals from the card into the archive")
    card_args(sp)
    sp.add_argument("--name", help="label appended to the shoot folder, e.g. brighton-beach")
    sp.add_argument("-n", "--dry-run", action="store_true", help="show the plan, copy nothing")
    sp.set_defaults(func=cmd_ingest)

    def derive_args(sp):
        sp.add_argument("paths", nargs="*", help="shoot folders (default: the whole archive)")
        sp.add_argument("--source", choices=["auto", "jpg", "raw"], default="auto",
                        help="which original to render from (default: auto, prefers the camera JPEG)")
        sp.add_argument("-o", "--out", help="output directory (default: the mirrored path under the web root)")
        sp.add_argument("-j", "--jobs", type=int, default=4, help="parallel conversions (default: 4)")
        sp.add_argument("-f", "--force", action="store_true", help="re-render even if up to date")

    sp = sub.add_parser("derive", help="render resized JPEGs into the web tree")
    derive_args(sp)
    sp.add_argument("--preset", default="web", help="derive preset from the config (default: web)")
    sp.add_argument("--subdir", help="write into this subdirectory of the output")
    sp.set_defaults(func=cmd_derive)

    sp = sub.add_parser("gallery", help="render derivatives plus a browsable index.html")
    derive_args(sp)
    sp.add_argument("--no-index", action="store_true", help="skip the parent index pages")
    sp.set_defaults(func=cmd_gallery)

    sp = sub.add_parser("inspect", help="what cameras and dates are in a folder of unsorted originals")
    sp.add_argument("paths", nargs="+", help="folders (or files) to survey")
    sp.add_argument("--dest", help="archive root to suggest destinations under (default: from config)")
    sp.add_argument("--files", action="store_true", help="also list every file with its capture time")
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("review", help="browse the ingested days in the browser to keep, reject, rate and group")
    sp.add_argument("target", nargs="?", help="open one day directly: a date (2026-09-13) or a folder; default is the day list")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--lan", action="store_true", help="listen on all interfaces so a tablet on the LAN can join")
    sp.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    sp.set_defaults(func=cmd_review)

    sp = sub.add_parser("sync", help="rsync the archive and web trees to the NAS")
    sp.add_argument("which", nargs="?", choices=["archive", "web", "both"], default="both")
    sp.add_argument("-n", "--dry-run", action="store_true")
    sp.add_argument("--delete", action="store_true", help="remove files at the target that are gone here")
    sp.set_defaults(func=cmd_sync)

    args = p.parse_args(argv)
    cfg = config.load(args.config)
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
