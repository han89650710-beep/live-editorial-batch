#!/usr/bin/env python3
"""Update this skill in place without touching the client's own files.

  python scripts/update.py            # update to the latest release
  python scripts/update.py --check    # only report local vs remote version

What it keeps untouched (everything you or the client authored):
  config.json, stories/, work/, output/, node_modules/

Two update paths:
  * a git clone  -> git fetch + fast-forward merge
  * a zip install -> download the latest zip and replace code files only

Optional: --deps re-installs Python/npm dependencies after a code update.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "han89650710-beep/live-editorial-batch"
BRANCH = "main"
RAW_PACKAGE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/package.json"
ZIP_URL = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
KEEP_TOP = {"config.json", "stories", "work", "output", "node_modules",
            "demo_source.mp4", "__pycache__"}
SKIP_PARTS = {".git", "node_modules", "__pycache__"}


def local_version() -> str:
    path = ROOT / "package.json"
    try:
        return str(json.loads(path.read_text(encoding="utf-8-sig")).get("version", "0.0.0"))
    except (OSError, json.JSONDecodeError):
        return "0.0.0"


def remote_version() -> str | None:
    # The timestamp busts the CDN cache so a fresh release is visible at once.
    url = f"{RAW_PACKAGE}?t={int(time.time())}"
    request = urllib.request.Request(url, headers={"User-Agent": "live-editorial-batch",
                                                  "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data.get("version", "0.0.0"))
    except Exception as error:  # offline, blocked, or repo moved
        print(f"[update] cannot reach GitHub: {error}", file=sys.stderr)
        return None


def is_newer(remote: str, local: str) -> bool:
    def parts(value: str) -> tuple[int, ...]:
        digits = []
        for piece in value.split("."):
            number = "".join(ch for ch in piece if ch.isdigit())
            digits.append(int(number) if number else 0)
        return tuple(digits)

    return parts(remote) > parts(local)


def is_git_checkout() -> bool:
    return (ROOT / ".git").exists() and shutil.which("git") is not None


def git_update() -> bool:
    print("[update] git clone detected, fast-forwarding")
    commands = [
        ["git", "-C", str(ROOT), "fetch", "--depth", "1", "origin", BRANCH],
        ["git", "-C", str(ROOT), "merge", "--ff-only", f"origin/{BRANCH}"],
    ]
    for command in commands:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            print(result.stdout[-2000:], file=sys.stderr)
            print("[update] git update failed. Commit or discard local edits, then retry.",
                  file=sys.stderr)
            return False
    return True


def zip_update() -> bool:
    print("[update] zip install detected, downloading the latest code")
    with tempfile.TemporaryDirectory(prefix="leb-update-") as work:
        archive = Path(work) / "latest.zip"
        request = urllib.request.Request(ZIP_URL, headers={"User-Agent": "live-editorial-batch"})
        with urllib.request.urlopen(request, timeout=60) as response:
            archive.write_bytes(response.read())
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(work)
        roots = [item for item in Path(work).iterdir() if item.is_dir()]
        if not roots:
            print("[update] unexpected archive layout", file=sys.stderr)
            return False
        fresh = roots[0]
        copied = 0
        for source in fresh.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(fresh)
            if relative.parts[0] in KEEP_TOP or SKIP_PARTS & set(relative.parts):
                continue
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
        print(f"[update] {copied} files refreshed")
    return True


def install_deps() -> None:
    for command in (["pip", "install", "-r", "requirements.txt"], ["npm", "install"]):
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace")
        state = "ok" if result.returncode == 0 else "failed"
        print(f"[update] {' '.join(command)}: {state}")
        if result.returncode != 0:
            print(result.stdout[-1500:], file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update the skill without touching your files")
    parser.add_argument("--check", action="store_true", help="only compare versions")
    parser.add_argument("--deps", action="store_true", help="reinstall dependencies afterwards")
    parser.add_argument("--force-zip", action="store_true", help="ignore git and replace code files")
    args = parser.parse_args()

    local = local_version()
    remote = remote_version()
    if remote is None:
        print(f"[update] local {local}; cannot check for updates")
        raise SystemExit(1)
    print(f"[update] local {local} / remote {remote}")

    if not is_newer(remote, local):
        print("[update] already up to date")
        return
    if args.check:
        print("[update] a newer release is available; run without --check to apply it")
        return

    ok = zip_update() if args.force_zip or not is_git_checkout() else git_update()
    if not ok:
        raise SystemExit(1)
    print(f"[update] updated {local} -> {remote}")
    print("[update] kept: config.json, stories/, work/, output/, node_modules/")
    if args.deps:
        install_deps()
    else:
        print("[update] dependencies unchanged; pass --deps if doctor.py reports missing ones")


if __name__ == "__main__":
    main()
