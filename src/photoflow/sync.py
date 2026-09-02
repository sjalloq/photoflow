"""Push the archive and web trees to the NAS with rsync."""

import shutil
import subprocess
import sys
from pathlib import Path


def _run(source, target, dry_run=False, delete=False, report=print):
    source = Path(source).expanduser()
    if not source.is_dir():
        report(f"skipping {source}: no such directory")
        return 0
    # The trailing slash makes rsync copy the contents rather than nesting the
    # directory inside the target — the difference between web/ and web/web/.
    cmd = ["rsync", "-a", "--partial", "--human-readable", "--info=progress2",
           f"{source}/", target]
    if dry_run:
        cmd.insert(1, "--dry-run")
    if delete:
        cmd.insert(1, "--delete")
    report(f"{'(dry run) ' if dry_run else ''}{source} -> {target}")
    # rsync writes straight to the terminal; flush so our line lands first.
    sys.stdout.flush()
    return subprocess.run(cmd).returncode


def run(cfg, which="both", dry_run=False, delete=False, report=print):
    if not shutil.which("rsync"):
        sys.exit("rsync not found — install with: sudo pacman -S rsync")

    jobs = []
    if which in ("archive", "both"):
        jobs.append(("archive", cfg.archive, cfg.sync.get("archive_target", "")))
    if which in ("web", "both"):
        jobs.append(("web", cfg.web, cfg.sync.get("web_target", "")))

    status = 0
    for name, source, target in jobs:
        if not target:
            report(
                f"no {name} target configured — set sync.{name}_target in "
                f'the config file, e.g. "nas:/volume1/photo/{name}"'
            )
            continue
        status |= _run(source, target, dry_run, delete, report)
    return status
