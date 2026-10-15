"""DRAFT, NOT FOR APPROVAL: judge-host-prepare.

Prepares the pinned judge runtime on the one EC pool host Nelson names, inside
that host's EC workload cache, and records the host's hardware. It makes no
judgment and loads no model into memory.

Refuses unless NAMED_HOST and the Ollama pins in workloads/judge_common.py are
filled in (both are blank or "<TO-PIN>" in this draft), and never runs on a
work machine.

Steps:
1. Hardware readout (CPU, RAM, GPU, VRAM, disk) into out/hardware.json.
2. At least MIN_FREE_BYTES free on the cache drive, else stop.
3. The portable Ollama zip: downloaded once into the cache, its sha256 checked
   against OLLAMA_ZIP_SHA256 on every run, extracted once into
   ollama/<version>/.
4. Before any model download: the registry manifest of each approved tag must
   hash to its approved digest. A tag that now resolves to another digest
   stops the job (BLOCKED: a different digest is a different engine, SPEC §1).
5. `ollama.exe serve` from the cache on a private loopback port, version
   checked; each model pulled into OLLAMA_MODELS inside the cache unless it is
   already there.
6. Verification: each local manifest hashes to its approved digest, every
   layer and config blob has its declared size and sha256, and /api/tags
   reports the approved digests.
7. The server is stopped. out/prepare.json and out/SUMMARY.md.

Removal path: delete EC_WORKLOAD_CACHE (%LOCALAPPDATA%\\EC\\workloads\\taipei49314\\gavel
on that host); nothing is installed elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import judge_common as jc  # noqa: E402

WORKLOAD = "judge-host-prepare"
MIN_FREE_BYTES = 40 * 1024 ** 3  # 35b about 23.9 GB, 9b about 6.6 GB, runtime and margin
PULL_TIMEOUT_S = 4 * 3600


def download(url: str, target: Path, expected_sha256: str) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    fetched = False
    if not target.is_file():
        partial = target.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=600) as response, open(partial, "wb") as fh:
            shutil.copyfileobj(response, fh, 1 << 22)
        os.replace(partial, target)
        fetched = True
    actual = jc.sha256_file(target)
    if actual != expected_sha256:
        target.unlink()
        raise RuntimeError(f"Ollama zip sha256 {actual} is not the pinned {expected_sha256}")
    return {"url": url, "sha256": actual, "downloaded_now": fetched, "bytes": target.stat().st_size}


def extract(zip_path: Path, runtime: Path) -> dict:
    if not (runtime / "ollama.exe").is_file():
        staging = runtime.with_name(runtime.name + ".staging")
        if staging.exists():
            shutil.rmtree(staging)
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                if member.startswith(("/", "\\")) or ".." in Path(member).parts:
                    raise RuntimeError(f"unsafe path in the Ollama zip: {member}")
            archive.extractall(staging)
        runtime.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, runtime)
    return {"ollama_exe_sha256": jc.sha256_file(runtime / "ollama.exe")}


def registry_check(out: Path) -> dict:
    results = {}
    for model, expected in jc.MODELS.items():
        name, tag = model.split(":", 1)
        request = urllib.request.Request(f"{jc.REGISTRY}/v2/library/{name}/manifests/{tag}",
                                         headers={"Accept": jc.MANIFEST_ACCEPT})
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
        (out / "registry").mkdir(parents=True, exist_ok=True)
        (out / "registry" / f"{name}-{tag}.manifest.json").write_bytes(body)
        actual = hashlib.sha256(body).hexdigest()
        results[model] = {"expected": expected, "registry_sha256": actual,
                          "ok": actual == expected}
    return results


def main() -> int:
    try:
        paths = jc.gate(WORKLOAD)
    except jc.Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    out, record, problems = paths["out"], {"workload": WORKLOAD, "host": paths["host"]}, []
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    record["hardware"] = jc.hardware(paths["cache"])
    jc.write_json(out / "hardware.json", record["hardware"])
    try:
        paths["cache"].mkdir(parents=True, exist_ok=True)
        if record["hardware"]["disk"]["free"] < MIN_FREE_BYTES:
            raise RuntimeError("not enough free disk on the cache drive")
        zip_path = paths["zip_dir"] / f"{jc.OLLAMA_ZIP_SHA256}.zip"
        record["ollama_zip"] = download(jc.OLLAMA_ZIP_URL, zip_path, jc.OLLAMA_ZIP_SHA256)
        record["runtime"] = extract(zip_path, paths["runtime"])
        record["registry"] = registry_check(out)
        if not all(item["ok"] for item in record["registry"].values()):
            raise RuntimeError("BLOCKED: a registry tag no longer resolves to its approved "
                               "digest; a different digest is a different engine (SPEC §1)")
        with jc.OllamaServer(paths, out / "ollama-serve.log") as server:
            record["ollama_version"] = server.version
            record["pulled"] = {}
            for model in jc.MODELS:
                if jc.verify_local_model(paths["models"], model, blobs=False)["ok"]:
                    record["pulled"][model] = "already present"
                    continue
                jc.http_json("POST", f"{server.base_url}/api/pull",
                             {"model": model, "stream": False}, timeout=PULL_TIMEOUT_S)
                record["pulled"][model] = "pulled"
            record["tags"] = server.tags()
        record["models"] = {m: jc.verify_local_model(paths["models"], m, blobs=True)
                            for m in jc.MODELS}
        for model, expected in jc.MODELS.items():
            if record["tags"].get(model) != expected:
                problems.append(f"{model}: /api/tags digest {record['tags'].get(model)} is not "
                                f"the approved {expected}")
            if not record["models"][model]["ok"]:
                problems.append(f"{model}: local manifest or blobs do not verify")
    except Exception as exc:  # recorded, then the job fails
        problems.append(f"{type(exc).__name__}: {exc}")
    record["seconds"] = round(time.monotonic() - started, 1)
    record["problems"] = problems
    record["passed"] = not problems
    jc.write_json(out / "prepare.json", record)
    lines = ["# judge-host-prepare (DRAFT workload)", "",
             f"Result: {'PASS' if not problems else 'FAIL'} on {paths['host']}", "",
             f"- Ollama: {record.get('ollama_version')} (pinned {jc.OLLAMA_VERSION}); zip sha256 "
             f"{record.get('ollama_zip', {}).get('sha256')}",
             f"- Registry manifests: {json.dumps(record.get('registry'), sort_keys=True)}",
             "- Local models: " + ", ".join(f"{m}: {'ok' if v.get('ok') else 'NOT OK'}"
                                             for m, v in record.get('models', {}).items()),
             "- No judgment was made and no model was loaded.", ""]
    lines += [f"- problem: {p}" for p in problems]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
