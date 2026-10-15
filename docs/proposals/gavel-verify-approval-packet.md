# gavel-verify: EC pool workload approval packet (draft)

Status: draft prepared 2026-10-15 on branch `fix/exam-validity`. Nothing here is
approved. The workload has not run anywhere:
`NOT_RUN：工作機規則（POLICY work-machine-local），gavel-verify runs only on the EC pool, after Nelson approves this entry`.

**[Note 2026-10-15]** This packet predates Nelson's standing authorization of
2026-10-15T09:49:47Z (EC POLICY `gavel-pju-execution`; see AGENTS.md and
docs/DECISIONS.md), which for gavel on LAPTOP-01AGNPJU supersedes D2(A)'s
venue part. This packet describes the EC pool route only; the workload script
still refuses to run on the work machines and is not the PJU route.

This packet follows the format of the ledgerwash `v03-verify` approval
(EC `evidence/requests/5a6a51ab-8686-46a1-b85c-7dc3902442af/ledgerwash-pool-approval.md`).
It asks for one L2 decision: approval of one workload declaration entry.

## What is asked

Approve the `gavel-verify` entry of `ec-workloads.json` in taipei49314/gavel, so
that EC may register it and run it, at exact gavel commits, on an EC pool
workload listener.

| Item | Value |
|---|---|
| Repository | taipei49314/gavel (public) |
| Candidate SHA | fixed when batch 2 (branch `fix/exam-validity`) is pushed; batch 2 needs Nelson's named publication OK first (decision D5(a)) |
| Declaration | `ec-workloads.json` at the repository root: `https://github.com/taipei49314/gavel/blob/<SHA>/ec-workloads.json` |
| Workload | `gavel-verify` |
| Canonical entry sha256 | `904bc04051be90899c85efdc2a90f34687281db7f3c1eb9313d71717c476f55a` |
| Entry script | `workloads/gavel_verify/run.py` (helpers `round2.py`, `legacy_round2.py`, `round2_papers.json` in the same directory) |
| Profile | `profile-ec-integrity` |
| Timeout | 30 minutes |
| Cache | false |
| Parameters | none |
| Host | any workload listener; the script itself refuses LAPTOP-01AGNPJU and LAPTOP-16NUA5I8 |

### How the entry sha256 was computed

The same way `tools/pool/workload.py` computes `entry_sha256()`:
`sha256(json.dumps(entry, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))`
over the `gavel-verify` object of `ec-workloads.json` (read as UTF-8, duplicate
keys refused). It was computed with `python -I` and the standard library only.
The method was cross-checked on the precedent: the same computation over the
ledgerwash `v03-verify` entry at ledgerwash commit `5a7687a4` gives
`aaebc886e9c469953b204d48e398e20ccb7fdd0942e622c6936774464f942e13`, the value
EC records in `governance/pool/workloads.json`.

Any change to the entry, including its description, changes this hash and
needs a new approval. Changes to the scripts do not change the hash; EC runs
them only at an exact commit, and each run's receipt names that commit.

## Scope

On one pool host, at one exact commit, with no model:

1. Checks its identity (EC workload variables, repository, workload name,
   exact SHA, clean checkout) and refuses to run on the two work machines.
2. Creates a venv in the job's work directory and installs only the six
   pure-Python pytest wheels (pytest, colorama, iniconfig, packaging, pluggy,
   pygments) pinned by sha256 in the committed `uv.lock`, with
   `pip --require-hashes --no-deps --only-binary=:all: --no-cache-dir`. This
   PyPI download is its only network access. It checks that `pyproject.toml`
   declares no runtime dependency.
3. Runs the full test suite with a JUnit report and fails on any failure,
   error or skip, or on zero tests.
4. Runs `gavel verify --content` on every committed receipts file
   (`git ls-files '*.jsonl'`; six files at d0cb1dc).
5. Runs `round2.py` twice, in separate processes, at `PYTHONHASHSEED` 1 and 17.
   Each run:
   - rebuilds every round-2 prompt from the committed case files with the
     frozen anchor v1 renderer and the prompt v4 header, and compares text and
     sha256 with all 149 round-2 receipts (110 regression, 39 sealed);
   - regenerates the round-2 tables from the committed receipts **as locked**
     (PREREG Addendum 4 and 5: first attempt of every cell, attempt cap 1,
     later attempts listed and not counted; the papers are reconstructed in
     `round2_papers.json`) and **as reported** (`evaluate()` exactly as it
     stood at d0cb1dc, copied byte for byte into `legacy_round2.py`, over every
     receipt with the last receipt per cell winning, with the arguments the
     operator session log records), and compares the latter with the
     committed `report.json` files and the computed rows of `scoring.md`.

   The run fails unless every prompt matches and both seeds give
   byte-identical outputs. The table contents are reported, not gated.
6. Checks again that the source SHA and the clean checkout are unchanged.

Steps 1-5 share a 25-minute budget inside the 30-minute entry timeout: each
step's own timeout is cut to the time left, and a step that would start
after the budget is spent is skipped and recorded as a problem (the run then
fails), so `result.json` and `SUMMARY.md` are always written before EC ends
the job. The two step-6 git checks get one more minute of their own. This is
script behaviour; the entry, and so its sha256 above, is unchanged
(recomputed after the change: `904bc040…f55a`).

It writes `out/result.json` (source SHA, host, runtime, uv.lock sha256,
requirements, every command with exit code, duration and output hashes, JUnit
counts, receipts files and their sha256, round-2 output hashes), `out/suite.xml`,
`out/logs/`, `out/round2/seed-1/` and `out/round2/seed-17/`, and
`out/SUMMARY.md`, which EC copies into the check run.

## Exclusions

- No model call of any kind: no Ollama, no agy, no codex, no cloud API. The
  script points `GAVEL_OLLAMA` at a closed local port and `GAVEL_AGY` at a
  path that does not exist, so an accidental call fails closed.
- No judgment is reproduced. A pass does not qualify the judge, does not
  change the round-2 status of record (INCOMPLETE, decision D1(a)) and does
  not accept any result produced on a work machine: round-0, round-1, attack
  round-1 (M4 wave-1) and round-2 stay 「未驗收」.
- No release, tag, package publication or push. No change to the SPEC.
- No host change, runner provisioning, service install, App permission
  expansion, credential access or security setting. `cache` is false.
- No local product tests on a work machine.
- The draft judge workloads in `workloads/ec-workloads.drafts.json`
  (`judge-host-prepare`, `judge-smoke`, `gavel-exam`) are not part of this
  approval. That file is not a top-level declaration, so EC cannot register
  them from it.

## Expected observations (predictions, not results)

From the committed receipts, read without running gavel:

- As locked: round-2-regression INCOMPLETE (CW-A07/fast/1 has no valid first
  attempt); round-2-sealed INCOMPLETE (SP-004/fast/1 and SP-007/fast/1); four
  later attempts recorded and not counted (CW-A07 fast attempt 2; SP-004 fast
  attempt 2; SP-007 fast attempts 2 and 3). This is the status of record that
  Nelson adopted on 2026-10-15 (D1(a)). The two calls that left no receipt
  cannot appear here.
- As reported: the d0cb1dc `evaluate()` with the as-run arguments is expected
  to reproduce both committed `report.json` files (regression PASS with fast
  divergence `['CW-A07', 'LW-R8']`; sealed INCOMPLETE on SP-007/fast/1). This
  is the reconstruction in takeover audit findings CR-01 and CR-03; the run
  confirms or refutes it.

## Before the first dispatch (separate gates)

1. Nelson's named publication OK for batch 2, which fixes the candidate SHA.
2. Nelson's approval of this entry, by its sha256 (L2).
3. The workload App `taipei49314-ec-pool-workload` (contents:read,
   checks:write) installed on taipei49314/gavel, by Nelson or by the agent on
   his explicit OK (T-464 pattern). EC `governance/pool/apps.json` lists four
   repositories today and gavel is not among them.
4. An EC task row for registration and dispatch through the manual v2
   `ec_task` route. T-533's recorded human instruction excludes gavel:
   「不讀、改、import、安裝、呼叫或部署 gavel」
   (EC `evidence/requests/a6c61134-18a2-475d-80ee-c6fc9127a7b2/human-instruction.md`).
5. An EC PR that adds taipei49314/gavel to `apps.json` (workload repositories),
   to the repository options of `pool-workload.yml`, and to
   `governance/pool/workloads.json` with this sha256 and the decision evidence
   path.

Routine fixes within this declared scope run at new exact SHAs; a changed
entry needs a new approval.
