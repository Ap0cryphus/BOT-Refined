#!/usr/bin/env python3
"""
==============================================================================
rollback_verify.py - dry-run validation of every rollback target
==============================================================================
Called by `rollback.bat verify`. It NEVER touches your working tree.

  Level 1  the files currently in the project (git HEAD)
  Level 2  _prefeval_backup\\            (pre-evaluation build)
  Level 3  git bc1d29f                  (the complete original codebase)

For each level it extracts/copies the files into a temp folder and parses them
with ast.parse(). A level passes only if every file parses.

Exit code 0 = all levels usable, 1 = at least one broken.
==============================================================================
"""

import ast
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
ORIGIN = "bc1d29f"
CODE = ["kaekae_bot.py", "cef_probe.py", "cef_explorer.py", "chat_worker.py",
        "master_dashboard.py", "audio_worker.py", "launch_kaekae.py",
        "calibrate_camfrog.py"]
PRE = "_prefeval_backup"


def parse_dir(folder, prefix):
    """Parses every *.py in folder. Returns (ok_list, broken_list)."""
    ok, broken = [], []
    for path in sorted(glob.glob(os.path.join(folder, "*.py"))):
        name = os.path.basename(path)
        try:
            ast.parse(open(path, encoding="utf-8").read())
            ok.append(f"{prefix}{name}")
        except SyntaxError as e:
            broken.append(f"{prefix}{name} (line {e.lineno}: {e.msg})")
    return ok, broken


def git_show(commit, path):
    try:
        r = subprocess.run(["git", "show", f"{commit}:{path}"],
                           cwd=ROOT, capture_output=True, timeout=30)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def main():
    levels = []
    tmp = tempfile.mkdtemp(prefix="kaekae_rollback_verify_")

    # ---- Level 1: what is in the project right now (HEAD) --------------
    d1 = os.path.join(tmp, "l1")
    os.makedirs(d1, exist_ok=True)
    for f in CODE:
        src = os.path.join(ROOT, f)
        if os.path.exists(src):
            shutil.copy(src, d1)
    levels.append(("LEVEL 1  git HEAD (current build)", *parse_dir(d1, "")))

    # ---- Level 2: the pre-evaluation backup folder ---------------------
    d2 = os.path.join(tmp, "l2")
    os.makedirs(d2, exist_ok=True)
    pre_dir = os.path.join(ROOT, PRE)
    if os.path.isdir(pre_dir):
        for f in CODE:
            src = os.path.join(pre_dir, f)
            if os.path.exists(src):
                shutil.copy(src, d2)
        levels.append((f"LEVEL 2  {PRE}\\ (pre-evaluation build)",
                       *parse_dir(d2, "")))
    else:
        levels.append((f"LEVEL 2  {PRE}\\ (pre-evaluation build)", [],
                       ["FOLDER MISSING"]))

    # ---- Level 3: the complete original codebase from git --------------
    d3 = os.path.join(tmp, "l3")
    os.makedirs(d3, exist_ok=True)
    missing = []
    for f in CODE:
        blob = git_show(ORIGIN, f)
        if blob is None:
            missing.append(f"{f} (not in {ORIGIN})")
        else:
            with open(os.path.join(d3, f), "wb") as fh:
                fh.write(blob)
    ok3, bad3 = parse_dir(d3, "")
    levels.append((f"LEVEL 3  git {ORIGIN} (original codebase)", ok3,
                   bad3 + missing))

    shutil.rmtree(tmp, ignore_errors=True)

    print("  " + "=" * 74)
    all_ok = True
    for name, ok, bad in levels:
        status = "USABLE" if ok and not bad else "PROBLEM"
        print(f"  {name:<46} {len(ok):>2} parsed   {status}")
        for b in bad:
            print(f"        !! {b}")
        if bad or not ok:
            all_ok = False
    print("  " + "=" * 74)

    if not all_ok:
        print("\n  RESULT: at least one level is NOT fully usable.")
        return 1

    print("\n  RESULT: all three rollback levels are usable.")
    print("  Level 3 note: it is the COMPLETE original codebase - prefer it")
    print("  over _presync_backup\\, which holds only 6 files and would leave")
    print("  the new cef_explorer/chat_worker/calibrate_camfrog in place.")
    return 0


if __name__ == "__main__":
    sys.exit(main())