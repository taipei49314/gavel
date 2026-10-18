"""Operator load check before a round-3 stage-1 paper. Not a PREREG step:
added 2026-10-18 after paper R, disclosed in each <paper>-load.txt.

    python -B loadcheck.py <worktree> <paper>

Loads the paper's arm model once through the local Ollama daemon (an empty
prompt, the manifest's options), records the device placement the server log
shows, unloads it, and waits until /api/ps lists none. No judgment is made and
no receipt is written. The placement is compared with a reference load:

- primary: the first load of paper R run 1 (results/round-3/R/run-1/ollama-load.txt);
- fast: the fresh-load smoke session's fast loads (Ollama server.log,
  2026-10-17T04:37 +0800; values copied below).

Writes results/round-3/lock-check/<paper>-load.txt in the worktree. Exits 0
when the placement matches, 1 when it does not, 2 when the check could not
run. It does not commit."""

import ctypes
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1]).resolve()
paper = sys.argv[2]
PAPERS = {"R": "cases/round-3-R.manifest.json", "K": "cases/round-3-K.manifest.json",
          "R-fast": "cases/round-3-R-fast.manifest.json",
          "K-fast": "cases/round-3-K-fast.manifest.json"}
BASE = "http://127.0.0.1:11434"
SERVER_LOG = Path(os.environ["LOCALAPPDATA"]) / "Ollama" / "server.log"

# Lines that describe where the model's tensors go. The "projected ... free
# device memory" line is recorded but not compared: it is an input to the fit.
PLACEMENT = [
    re.compile(r"cannot meet free memory target|will leave .* no changes needed"),
    re.compile(r"set ngl_per_device\[0\]\.\(n_layer, n_part, overflow_type\)="),
    re.compile(r"CUDA0 \(.*\): \d+ layers \(\d+ overflowing\)"),
    re.compile(r"offloaded \d+/\d+ layers to GPU"),
    re.compile(r"model buffer size"),
    re.compile(r"KV buffer size"),
]
RECORD = PLACEMENT + [re.compile(r"projected to use"), re.compile(r"starting llama-server")]

FAST_REFERENCE = [
    "common_params_fit_impl: will leave N >= 1919 MiB of free device memory, no changes needed",
    "load_tensors: offloaded 34/34 layers to GPU",
    "load_tensors:        CUDA0 model buffer size =  4717.38 MiB",
    "load_tensors:    CUDA_Host model buffer size =   545.63 MiB",
    "llama_kv_cache:      CUDA0 KV buffer size =   272.00 MiB",
]


def norm(line: str) -> str:
    """Drop the timestamp, the port and the free-memory amounts: those vary
    between loads without changing where the tensors go."""
    line = re.sub(r"^time=\S+ ", "", line.rstrip("\r\n"))
    line = re.sub(r"--port \d+ ", "", line)
    line = re.sub(r"(\d+ layers \(\d+ overflowing\),\s+\d+ MiB used),\s+\d+ MiB free", r"\1", line)
    line = re.sub(r"need to reduce device memory by \d+ MiB", "need to reduce device memory by N MiB", line)
    return re.sub(r"will leave \d+ >=", "will leave N >=", line)


def pick(lines, patterns):
    return [norm(l) for l in lines if any(p.search(l) for p in patterns)]


def last_fit(lines):
    """Placement lines with only the final ngl_per_device setting kept."""
    out = pick(lines, PLACEMENT)
    sets = [l for l in out if "set ngl_per_device[0].(n_layer, n_part, overflow_type)=" in l]
    return [l for l in out if l not in sets[:-1]]


def api(method, path, body=None, timeout=600):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def available_mb():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    ms = MS()
    ms.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    return ms.ullAvailPhys // (1024 * 1024)


def gpu_free():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free,memory.used,utilization.gpu",
                              "--format=csv,noheader"], capture_output=True, text=True, timeout=30)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unreadable: {type(exc).__name__}"


lines_out = []
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
host = os.environ.get("COMPUTERNAME") or socket.gethostname()
manifest = json.loads((root / PAPERS[paper]).read_text(encoding="utf-8"))
arm = manifest["gating_arm"] if manifest.get("gating_arm") else next(iter(manifest["arms"]))
model = manifest["arms"][arm]["model"]
options = manifest.get("options") or {}
lines_out += [f"# Round-3 load check before paper {paper}", "",
              "Label: human-authorized local PJU, NOT EC pool (EC POLICY gavel-pju-execution, T-542).",
              "Not a PREREG step: an operator check added on 2026-10-18 after paper R, to record",
              "the device placement before the paper. No judgment, no receipt.",
              f"- host {host}; host clock {now}; paper {paper}; arm {arm}; model {model}; options {options}",
              f"- before: available RAM {available_mb()} MiB; nvidia-smi free,used,util {gpu_free()}"]

status = 2
try:
    loaded = [m.get("name") for m in api("GET", "/api/ps", timeout=30).get("models", [])]
    lines_out.append(f"- /api/ps before the load: {loaded}")
    if loaded:
        raise SystemExit("models are loaded before the check; nothing was changed")
    offset = SERVER_LOG.stat().st_size
    t0 = time.monotonic()
    resp = api("POST", "/api/generate", {"model": model, "options": options, "stream": False})
    lines_out.append(f"- load call: done_reason {resp.get('done_reason')!r}, "
                     f"load_duration {resp.get('load_duration')}, {time.monotonic() - t0:.1f} s")
    ps = api("GET", "/api/ps", timeout=30).get("models", [])
    lines_out.append("- /api/ps after the load: " + json.dumps(
        [{k: m.get(k) for k in ("name", "digest", "size", "size_vram", "context_length")} for m in ps]))
    lines_out.append(f"- during: available RAM {available_mb()} MiB; nvidia-smi free,used,util {gpu_free()}")
    api("POST", "/api/generate", {"model": model, "keep_alive": 0, "stream": False})
    deadline = time.monotonic() + 120
    while api("GET", "/api/ps", timeout=30).get("models"):
        if time.monotonic() > deadline:
            raise SystemExit("the model is still loaded 120 s after the unload request")
        time.sleep(1)
    lines_out.append("- /api/ps after the unload: []")
    time.sleep(2)
    with open(SERVER_LOG, "rb") as fh:
        fh.seek(offset)
        new = fh.read().decode("utf-8", "replace").splitlines()
    starts = [l for l in new if "starting llama-server" in l]
    lines_out.append(f"- server log: {len(starts)} llama-server start(s) since the load call")
    got_all = pick(new, RECORD)
    got = last_fit(new)
    if arm == "primary":
        ref_text = (root / "results/round-3/R/run-1/ollama-load.txt").read_text(encoding="utf-8").splitlines()
        idx = [i for i, l in enumerate(ref_text) if "starting llama-server" in l]
        block = ref_text[idx[0]:idx[1]]
        ref = last_fit(block)
        ref_cmd = pick(block, [re.compile("starting llama-server")])
        got_cmd = pick(new, [re.compile("starting llama-server")])
        cmd_ok = len(starts) == 1 and got_cmd == ref_cmd
        lines_out.append(f"[{'ok' if cmd_ok else 'FAIL'}] llama-server command (port removed) equals R run 1's first load")
        ref_src = "results/round-3/R/run-1/ollama-load.txt, first load"
    else:
        ref, cmd_ok = FAST_REFERENCE, len(starts) == 1
        ref_src = "fresh-load smoke, server.log 2026-10-17T04:37 +0800 (copied into this script)"
    place_ok = got == ref
    lines_out.append(f"[{'ok' if place_ok else 'FAIL'}] placement lines equal the reference ({ref_src})")
    lines_out += ["", "Reference placement:"] + [f"    {l}" for l in ref]
    lines_out += ["", "This load (recorded lines):"] + [f"    {l}" for l in got_all]
    status = 0 if (cmd_ok and place_ok) else 1
except SystemExit as exc:
    lines_out.append(f"[FAIL] {exc}")
except Exception as exc:  # recorded; the check did not run
    lines_out.append(f"[FAIL] check did not run: {type(exc).__name__}: {exc}")

lines_out += ["", f"Result: {'PLACEMENT MATCHES' if status == 0 else ('PLACEMENT DIFFERS' if status == 1 else 'CHECK DID NOT RUN')}", ""]
out = root / "results" / "round-3" / "lock-check" / f"{paper}-load.txt"
out.write_bytes("\n".join(lines_out).encode("utf-8"))
print("\n".join(lines_out))
sys.exit(status)
