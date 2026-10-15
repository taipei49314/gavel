"""DRAFT, NOT FOR APPROVAL: shared code of the judge-host workload drafts.

Used by workloads/judge_host_prepare, workloads/judge_smoke and
workloads/gavel_exam, which are declared only in
workloads/ec-workloads.drafts.json. None of them may run until:

- Nelson names the EC pool host (NAMED_HOST below; blank refuses) and the
  scope (portable Ollama plus about 30 GB of model files in that host's EC
  workload cache, no service install, removal = delete the cache directory),
  as a host operation entered in the EC ledger first (EC POLICY
  host-operations);
- the Ollama runtime is pinned (OLLAMA_VERSION, OLLAMA_ZIP_URL and
  OLLAMA_ZIP_SHA256; "<TO-PIN>" refuses);
- Nelson approves each final declaration entry by its sha256 (L2).

Everything lives under EC_WORKLOAD_CACHE (the per-repository cache EC gives a
workload that declares "cache": true):

  ollama-zip/<sha256>.zip     the pinned portable Ollama archive
  ollama/<version>/           its extracted files (ollama.exe, lib/)
  ollama-models/              OLLAMA_MODELS: manifests/ and blobs/
  ollama-home/                USERPROFILE/HOME of the server process, so its
                              key pair and settings stay inside the cache

The server runs as `ollama.exe serve` from that directory only, bound to
127.0.0.1 on a free ephemeral port, and is stopped before the job ends (EC's
kill-on-close job object also ends it). The desktop app and its updater are
never started, so nothing updates itself. TO VERIFY ON THE POOL: that the
pinned server writes nothing outside the cache besides its log on stdout.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "taipei49314/gavel"
WORK_MACHINES = frozenset({"LAPTOP-01AGNPJU", "LAPTOP-16NUA5I8"})

# DRAFT: the EC pool host Nelson names (its COMPUTERNAME). Blank refuses.
NAMED_HOST = ""
# DRAFT: the pinned Ollama runtime. round-2 began on Ollama 0.35.0 (the
# version before the automatic upgrade to 0.40.4 at 03:37-03:38 +0800 on
# 2026-10-15); whether a 0.35.0 Windows zip is still downloadable is not known.
OLLAMA_VERSION = "<TO-PIN>"
OLLAMA_ZIP_URL = "<TO-PIN>"  # e.g. the ollama-windows-amd64.zip asset of that GitHub release
OLLAMA_ZIP_SHA256 = "<TO-PIN>"
PLACEHOLDER = "<TO-PIN>"

# approved-models.json digests (Ollama manifest sha256). A different digest is
# a different engine (SPEC §1), so a mismatch stops the job; it is never pulled
# "close enough".
MODELS = {
    "qwen3.5:35b-a3b": "3460ffeede5453ead027dbd2f821b12ad0aa3de54630971993babdb2165221f7",
    "qwen3.5:9b": "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7",
}
REGISTRY = "https://registry.ollama.ai"
MANIFEST_ACCEPT = "application/vnd.docker.distribution.manifest.v2+json"


class Refused(RuntimeError):
    """The job must not run here or in this form; nothing was changed."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


def gate(workload: str) -> dict:
    """Refuse unless this is the named host, the approved workload and a pinned runtime."""
    for key in ("EC_WORKLOAD_SOURCE", "EC_WORKLOAD_OUT", "EC_WORKLOAD_WORK", "EC_WORKLOAD_SHA"):
        if not os.environ.get(key):
            raise Refused("run only through the approved EC pool workload")
    if (os.environ.get("EC_WORKLOAD_REPOSITORY") != REPOSITORY
            or os.environ.get("EC_WORKLOAD_NAME") != workload
            or Path(os.environ["EC_WORKLOAD_SOURCE"]).resolve() != ROOT):
        raise Refused("unexpected workload identity")
    host = os.environ.get("COMPUTERNAME", "").upper()
    if not NAMED_HOST:
        raise Refused("DRAFT: no pool host has been named; this job runs nowhere")
    if host in WORK_MACHINES or platform.node().upper() in WORK_MACHINES:
        raise Refused("never on a work machine")
    if host != NAMED_HOST.upper() or platform.node().upper() != NAMED_HOST.upper():
        raise Refused(f"this job runs only on {NAMED_HOST}, not on {host or '?'}")
    if PLACEHOLDER in (OLLAMA_VERSION, OLLAMA_ZIP_URL, OLLAMA_ZIP_SHA256):
        raise Refused("DRAFT: the Ollama runtime is not pinned")
    cache = os.environ.get("EC_WORKLOAD_CACHE")
    if not cache:
        raise Refused("the entry must declare cache true")
    cache = Path(cache).resolve()
    return {"host": host, "out": Path(os.environ["EC_WORKLOAD_OUT"]).resolve(),
            "work": Path(os.environ["EC_WORKLOAD_WORK"]).resolve(),
            "cache": cache, "zip_dir": cache / "ollama-zip",
            "runtime": cache / "ollama" / OLLAMA_VERSION,
            "models": cache / "ollama-models", "home": cache / "ollama-home"}


def http_json(method: str, url: str, payload=None, timeout: float = 30.0):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def local_manifest_path(models: Path, model: str) -> Path:
    name, tag = model.split(":", 1)
    return models / "manifests" / "registry.ollama.ai" / "library" / name / tag


def verify_local_model(models: Path, model: str, *, blobs: bool) -> dict:
    """The local manifest must hash to the approved digest; with blobs=True
    every layer and the config blob must exist with its size and sha256."""
    path = local_manifest_path(models, model)
    record = {"model": model, "expected": MODELS[model], "manifest_present": path.is_file()}
    if not path.is_file():
        record["ok"] = False
        return record
    record["manifest_sha256"] = sha256_file(path)
    ok = record["manifest_sha256"] == MODELS[model]
    if blobs and ok:
        manifest = json.loads(path.read_bytes().decode("utf-8"))
        checked = []
        for layer in [manifest["config"]] + list(manifest["layers"]):
            algo, _, hexdigest = layer["digest"].partition(":")
            blob = models / "blobs" / f"{algo}-{hexdigest}"
            item = {"digest": layer["digest"], "size": layer.get("size"),
                    "present": blob.is_file()}
            if blob.is_file():
                item["size_ok"] = blob.stat().st_size == layer.get("size")
                item["sha256_ok"] = algo == "sha256" and sha256_file(blob) == hexdigest
            item["ok"] = bool(item.get("size_ok") and item.get("sha256_ok"))
            ok = ok and item["ok"]
            checked.append(item)
        record["blobs"] = checked
    record["ok"] = ok
    return record


class OllamaServer:
    """`ollama.exe serve` from the cache, on 127.0.0.1:<free port>, with its
    models and home inside the cache. Use as a context manager."""

    def __init__(self, paths: dict, log_path: Path):
        self.paths, self.log_path = paths, log_path
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.process = None
        self._log = None

    def environment(self) -> dict:
        home = self.paths["home"]
        tmp = self.paths["work"] / "ollama-tmp"
        for d in (home, tmp, self.paths["models"]):
            d.mkdir(parents=True, exist_ok=True)
        keep = ("SystemRoot", "windir", "SystemDrive", "ComSpec", "PATHEXT", "OS",
                "COMPUTERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
                "PROCESSOR_IDENTIFIER", "PATH")
        env = {k: os.environ[k] for k in keep if k in os.environ}
        env.update(USERPROFILE=str(home), HOME=str(home), LOCALAPPDATA=str(home / "AppData"),
                   APPDATA=str(home / "AppData"), TEMP=str(tmp), TMP=str(tmp),
                   OLLAMA_HOST=f"127.0.0.1:{self.port}", OLLAMA_MODELS=str(self.paths["models"]),
                   OLLAMA_NOPRUNE="1")
        return env

    def __enter__(self):
        exe = self.paths["runtime"] / "ollama.exe"
        if not exe.is_file():
            raise Refused("the pinned Ollama runtime is not prepared; run judge-host-prepare")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(self.log_path, "wb")
        cwd = self.paths["work"] / "ollama-cwd"
        cwd.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen([str(exe), "serve"], cwd=cwd, env=self.environment(),
                                        stdin=subprocess.DEVNULL, stdout=self._log,
                                        stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"ollama serve exited with {self.process.returncode}")
            try:
                self.version = http_json("GET", f"{self.base_url}/api/version", timeout=5)["version"]
                break
            except (OSError, urllib.error.URLError, ValueError, KeyError):
                time.sleep(1)
        else:
            raise RuntimeError("ollama serve did not answer within 120 s")
        if self.version != OLLAMA_VERSION:
            raise RuntimeError(f"ollama reports {self.version}, pinned {OLLAMA_VERSION}")
        return self

    def tags(self) -> dict:
        listed = http_json("GET", f"{self.base_url}/api/tags")
        return {m.get("name"): m.get("digest") for m in listed.get("models", [])}

    def __exit__(self, *exc):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=30)
        if self._log is not None:
            self._log.close()
        return False


def powershell_json(script: str, timeout: float = 120.0):
    """Run a read-only PowerShell query that prints JSON; None on failure."""
    exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / \
        "WindowsPowerShell" / "v1.0" / "powershell.exe"
    try:
        done = subprocess.run([str(exe), "-NoProfile", "-NonInteractive", "-Command",
                               script + " | ConvertTo-Json -Depth 4 -Compress"],
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        return json.loads(done.stdout.decode("utf-8", "replace") or "null")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def hardware(cache: Path) -> dict:
    """CPU, RAM, GPU, VRAM and disk, read only (CIM, the display-class
    registry key and nvidia-smi when present). AdapterRAM is a 32-bit field,
    so VRAM above 4 GB comes from HardwareInformation.qwMemorySize."""
    facts = {
        "cpu": powershell_json("Get-CimInstance Win32_Processor | Select-Object Name, "
                               "NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed"),
        "memory": powershell_json("Get-CimInstance Win32_ComputerSystem | Select-Object "
                                  "TotalPhysicalMemory, Model, Manufacturer"),
        "memory_free": powershell_json("Get-CimInstance Win32_OperatingSystem | Select-Object "
                                       "FreePhysicalMemory, TotalVisibleMemorySize, Caption, "
                                       "BuildNumber"),
        "gpu": powershell_json("Get-CimInstance Win32_VideoController | Select-Object Name, "
                               "AdapterRAM, DriverVersion, VideoProcessor"),
        "gpu_registry": powershell_json(
            "Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\"
            "{4d36e968-e325-11ce-bfc1-08002be10318}\\0*' -ErrorAction SilentlyContinue | "
            "Select-Object DriverDesc, 'HardwareInformation.qwMemorySize'"),
    }
    usage = shutil.disk_usage(cache if cache.exists() else cache.anchor)
    facts["disk"] = {"path_drive": str(Path(cache).drive), "total": usage.total,
                     "free": usage.free}
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            done = subprocess.run([smi, "--query-gpu=name,memory.total,driver_version",
                                   "--format=csv,noheader"], stdin=subprocess.DEVNULL,
                                  capture_output=True, timeout=60)
            facts["nvidia_smi"] = done.stdout.decode("utf-8", "replace").strip()
        except (OSError, subprocess.SubprocessError):
            facts["nvidia_smi"] = None
    return facts
