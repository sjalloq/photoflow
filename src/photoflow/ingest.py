"""Copy frames off a card into the archive, verified and idempotently.

Two rules govern everything here: the card is read-only as far as we are
concerned, and running twice must be indistinguishable from running once.
"""

import hashlib
import json
import os
import shutil
from datetime import datetime

from . import meta, paths

CHUNK = 1 << 20


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def classify(plans):
    """Mark each plan new / skip / conflict against what's already on disk.

    Size is the cheap discriminator: a re-ingest of the same card produces the
    same names, so a matching size is a match. Only a size mismatch is worth
    hashing, and only a genuine content difference earns a new name.
    """
    for plan in plans:
        if not plan.dest.exists():
            continue
        src = plan.frame.path
        if plan.dest.stat().st_size == src.stat().st_size:
            plan.status = "skip"
            continue
        if sha256(plan.dest) == sha256(src):
            plan.status = "skip"
            continue
        # Same name, different content — never overwrite an original.
        stem, suffix, n = plan.dest.stem, plan.dest.suffix, 1
        while plan.dest.exists():
            n += 1
            plan.dest = plan.dest.with_name(f"{stem}-{n}{suffix}")
        plan.status = "conflict"
    return plans


def copy_verified(src, dest):
    """Copy, prove it byte-identical, then keep it. Returns the digest.

    The copy lands on a .partial name first, so an interrupted run leaves no
    file that a later run would mistake for a completed one.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    shutil.copyfile(src, tmp)
    digest = sha256(src)
    if sha256(tmp) != digest:
        tmp.unlink(missing_ok=True)
        raise OSError(f"checksum mismatch copying {src}")
    stat = src.stat()
    os.utime(tmp, (stat.st_atime, stat.st_mtime))
    tmp.rename(dest)
    return digest


def load_manifest(directory):
    path = directory / paths.MANIFEST
    if not path.exists():
        return {"files": []}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        # The manifest is an audit trail, not state we depend on; a corrupt
        # one costs a rewrite, nothing more.
        return {"files": []}


def save_manifest(directory, camera, entries):
    """Append this run's entries, keyed by destination so re-runs don't grow it."""
    manifest = load_manifest(directory)
    known = {e["dest"]: e for e in manifest.get("files", [])}
    for entry in entries:
        known[entry["dest"]] = entry
    manifest["camera"] = camera.id
    manifest["updated"] = datetime.now().isoformat(timespec="seconds")
    manifest["files"] = sorted(known.values(), key=lambda e: e["dest"])
    (directory / paths.MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")


def run(card, archive, name=None, dry_run=False, report=print):
    """Plan, then execute, an ingest. Returns the shoots that were planned."""
    files = card.files()
    if not files:
        report(f"no images found on {card.path}")
        return []

    report(f"reading metadata for {len(files)} file(s)…")
    frames = meta.read(files)
    shoots = paths.plan_shoots(frames, card.camera, archive, name)
    for shoot in shoots:
        classify(shoot.plans)

    undated = sum(
        1 for s in shoots for p in s.plans if p.frame.dated_from != "exif"
    )
    if undated:
        report(f"note: {undated} file(s) had no EXIF capture time; used file mtime")

    for shoot in shoots:
        new = shoot.new
        conflicts = [p for p in shoot.plans if p.status == "conflict"]
        skipped = len(shoot.plans) - len(new) - len(conflicts)
        report(
            f"\n{shoot.directory}\n"
            f"  {len(shoot.plans)} file(s): {len(new)} new, "
            f"{skipped} already present, {len(conflicts)} renamed to avoid a clash"
        )
        if dry_run:
            for plan in new + conflicts:
                rel = plan.dest.relative_to(shoot.directory)
                report(f"    {plan.frame.path.name} -> {rel}")
            continue

        entries = []
        for plan in new + conflicts:
            digest = copy_verified(plan.frame.path, plan.dest)
            entries.append(
                {
                    "dest": str(plan.dest.relative_to(shoot.directory)),
                    "source": plan.frame.path.name,
                    "sha256": digest,
                    "bytes": plan.dest.stat().st_size,
                    "captured": plan.frame.captured.isoformat(timespec="seconds"),
                    "dated_from": plan.frame.dated_from,
                }
            )
            report(f"    {plan.frame.path.name} -> {plan.dest.name}")
        if entries:
            save_manifest(shoot.directory, card.camera, entries)
    return shoots
