"""Operator lock check before a round-3 stage-1 paper (PREREG Addendum 6,
"Papers"). Run with the worktree's venv python from anywhere:

    python -B lockcheck.py <worktree> <lock commit> <paper> <lock anchor>

Writes results/round-3/lock-check/<paper>.txt in the worktree and exits 0
only if every check passed. It does not commit.

This copy prints full sha256 values. R.txt was written by the earlier copy
(sha256 d00a5196...), which printed 12-character prefixes; the checks are the
same."""

import hashlib
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1]).resolve()
lock_arg, paper, anchor = sys.argv[2], sys.argv[3], sys.argv[4]
HEADING = "## Addendum 6 (round-3 stage-1 lock"
PAPERS = {"R": "cases/round-3-R.manifest.json", "K": "cases/round-3-K.manifest.json",
          "R-fast": "cases/round-3-R-fast.manifest.json",
          "K-fast": "cases/round-3-K-fast.manifest.json"}


def git(*args, binary=False):
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, stdin=subprocess.DEVNULL)
    if done.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.decode('utf-8', 'replace')}")
    return done.stdout if binary else done.stdout.decode("utf-8").strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


lines, ok = [], True


def check(cond, text):
    global ok
    lines.append(f"[{'ok' if cond else 'FAIL'}] {text}")
    ok = ok and bool(cond)


now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
host = os.environ.get("COMPUTERNAME") or socket.gethostname()
lock = git("rev-parse", "--verify", f"{lock_arg}^{{commit}}")
head = git("rev-parse", "HEAD")
branch = git("symbolic-ref", "--quiet", "--short", "HEAD")
lines += [f"# Round-3 lock check before paper {paper}", "",
          "Label: human-authorized local PJU, NOT EC pool (EC POLICY gavel-pju-execution, T-542).",
          f"Operator check required by PREREG Addendum 6 (\"Papers\"). Host clock {now}.",
          f"- host {host}; branch {branch}; HEAD {head}",
          f"- lock commit {lock}; lock anchor (GitHub push event) {anchor}", ""]

check(host.upper() == "LAPTOP-01AGNPJU", f"host is LAPTOP-01AGNPJU ({host})")
check(branch not in ("main", "master"), f"branch {branch} is a run branch, not main")
check(paper in PAPERS, f"paper {paper} is a stage-1 paper")
status = git("status", "--porcelain")
check(status == "", "working tree clean before this check (untracked files included)")
prereg_lock = git("show", f"{lock}:PREREG.md")
prereg_parent = git("show", f"{lock}^:PREREG.md")
check(HEADING in prereg_lock, "PREREG.md at the lock commit holds Addendum 6")
check(HEADING not in prereg_parent, "PREREG.md at the lock commit's parent has no Addendum 6")
changed_in_lock = sorted(p for p in git("diff", "--no-renames", "--name-only", f"{lock}^", lock).splitlines() if p)
check(changed_in_lock == ["PREREG.md", "docs/DECISIONS.md"],
      f"the lock commit changes only PREREG.md and docs/DECISIONS.md ({changed_in_lock})")
anc = subprocess.run(["git", "merge-base", "--is-ancestor", lock, head], cwd=root).returncode
check(anc == 0, "the lock commit is an ancestor of HEAD")
check(bool(git("branch", "-r", "--contains", lock)), "the lock commit is on a remote branch")
since = [p for p in git("diff", "--no-renames", "--name-only", lock, head).splitlines() if p]
outside = [p for p in since if not p.startswith("results/round-3/")]
check(not outside, f"git diff --no-renames --name-only <lock> HEAD lists only results/round-3/ paths "
                   f"({len(since)} paths; outside: {outside})")

addendum = prereg_lock[prereg_lock.index(HEADING):]
harness = re.findall(r"^  \| `([^`]+)` \| `([0-9a-f]{64})` \|$", addendum, re.M)
check(len(harness) == 12, f"harness table has 12 rows ({len(harness)})")
for path, want in harness:
    blob = sha(git("show", f"HEAD:{path}", binary=True))
    wt = sha((root / path).read_bytes())
    check(blob == want and wt == want, f"{path}: HEAD blob and working tree sha256 {want} "
                                       f"(blob {blob}, tree {wt})")
m = re.search(r"`approved-models\.json` sha256 `([0-9a-f]{64})`", addendum)
want = m.group(1) if m else None
got_blob = sha(git("show", "HEAD:approved-models.json", binary=True))
got_wt = sha((root / "approved-models.json").read_bytes())
check(want and got_blob == want and got_wt == want,
      f"approved-models.json sha256 {want} (blob {got_blob}, tree {got_wt})")
rows = re.findall(r"^  \| (R|K|R-fast|K-fast) \| `([^`]+)` \| `([0-9a-f]{64})` \|", addendum, re.M)
check(len(rows) == 4, f"papers table has 4 rows ({len(rows)})")
for name, path, want in rows:
    check(path == PAPERS[name], f"row {name} names {path}")
    blob = sha(git("show", f"HEAD:{path}", binary=True))
    wt = sha((root / path).read_bytes())
    check(blob == want and wt == want, f"row {name}: {path} sha256 {want} on its own row "
                                       f"(blob {blob}, tree {wt})")

m = re.search(r"instruction header sha256\s+`([0-9a-f]{64})`", addendum)
sys.path.insert(0, str(root))
from gavel.anchor import sha256_text  # noqa: E402
from gavel.prompt import INSTRUCTION_HEADER  # noqa: E402
header = sha256_text(INSTRUCTION_HEADER)
check(m and header == m.group(1), f"instruction header sha256 recomputed from gavel.prompt: {header}")
digests = re.findall(r"digest\s+`([0-9a-f]{64})`", addendum)
approved = json.loads((root / "approved-models.json").read_text(encoding="utf-8"))
approved_digests = set(re.findall(r"[0-9a-f]{64}", json.dumps(approved)))
check(len(digests) == 2 and set(digests) <= approved_digests,
      f"the two arm digests are in approved-models.json ({digests})")


def ollama(path):
    with urllib.request.urlopen(f"http://127.0.0.1:11434{path}", timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


try:
    version = ollama("/api/version").get("version")
    loaded = [x.get("name") for x in ollama("/api/ps").get("models", [])]
except Exception as exc:  # recorded, and fails the check
    version, loaded = f"unreadable: {type(exc).__name__}: {exc}", None
check(version == "0.40.4", f"Ollama /api/version is 0.40.4 ({version})")
lines.append(f"- /api/ps before the runner: {loaded}")
db = Path(os.environ["LOCALAPPDATA"]) / "Ollama" / "db.sqlite"
try:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = [r[1] for r in con.execute("pragma table_info(settings)")]
    auto = dict(zip(cols, con.execute("select * from settings").fetchone())).get("auto_update_enabled")
    con.close()
except Exception as exc:
    auto = f"unreadable: {type(exc).__name__}: {exc}"
check(auto == 0, f"Ollama app setting auto_update_enabled is 0 ({auto})")

lines += ["", f"Result: {'ALL CHECKS PASSED' if ok else 'CHECK FAILED'}", ""]
out = root / "results" / "round-3" / "lock-check" / f"{paper}.txt"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes("\n".join(lines).encode("utf-8"))
print("\n".join(lines))
sys.exit(0 if ok else 1)
