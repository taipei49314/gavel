# Round-3 stage-1 lock: candidate addendum (NOT LOCKED)

This file is the candidate text for round-3's stage-1 lock (round-3 PREREG
draft, section 10, item 7). Nothing in it is in force. If Nelson approves it,
the section below the line, with its `<APPROVAL>` placeholders (date, UTC
time and his words) filled from his approval, is appended verbatim to `PREREG.md`, and that commit, pushed, is the
lock commit. `tools/round3_run.py` refuses every paper until `PREREG.md` at
the lock commit holds this heading and names the paper's manifest sha256.

The rationale and history are in `docs/proposals/round-3-PREREG-DRAFT.md`; the
decisions it rests on are in `docs/DECISIONS.md` (2026-10-15 to 2026-10-17).

Revision 2 (2026-10-17). Nelson approved revision 1 (commit `d3ec7c7`) at
2026-10-17T15:39:34Z. The review run before locking it found a false
statement in its disclosure, a freeze clause that contradicted its own
stage-2 plan, an ambiguous use of "gaps", and checks the runner does not make
(docs/DECISIONS.md, 2026-10-17). This revision corrects them, names the
harness commit in the text (revision 1 left it as a placeholder), and changes
no hash, bar, option or paper. A second read-only review of this revision
tightened its wording. It is not approved yet; nothing is locked.

---

## Addendum 6 (round-3 stage-1 lock, <APPROVAL: date>)

- **Approval.** Nelson approved this text, the manifests, the harness commit
  `32c32983522fb3cd0257e5322ffe67e90cb3418b` and the runner script named below at
  `<APPROVAL: UTC time>` with 「<APPROVAL: his words>」 (docs/DECISIONS.md).
  This is stage 1 of a two-stage lock (adopted 2026-10-16T20:08:01Z): it
  locks papers R and K and their fast-arm observation papers, and the rules
  for N. N's case files, manifests and commitment are locked later as
  Addendum 7, under the rules fixed here.
- **Disclosure.** This design was written after round-2's results were known.
  Each rule answers a round-2 problem found by the takeover audit of
  2026-10-15 (round-3 PREREG draft, section 0). Completeness option (B) was
  chosen at 2026-10-15T17:23:48Z, during the first pre-lock smoke session and
  before its results were reported, on round-2's grounds (the cells round-2
  left without a valid verdict were all fast-arm cells). The load condition
  `fresh` was chosen at 2026-10-16T20:08:01Z, after the 2026-10-15 smoke
  sessions on LAPTOP-01AGNPJU showed that the fast arm's verdict on a case
  could depend on the case judged before it; the 2026-10-16 fresh-load
  session (results/round-3/prelock-smoke/fresh/) ran after that choice, to
  check it.
  Round-2 is not changed: both its papers stay INCOMPLETE and unaccepted
  (D1(a)).
- **Venue.** LAPTOP-01AGNPJU only, under EC POLICY `gavel-pju-execution`
  (T-542). Results are labelled "human-authorized local PJU, NOT EC pool".
- **Engine** (SPEC §1: a different digest is a different engine):
  - Prompt v4, instruction header sha256
    `ac22bc746831a994d4b5f75cde5f678ea2f4bb16abe7114570d0a71fb87984e3`;
    verdict schema v2 (attack, clean, inconclusive; four-part anatomy for
    attack; 11 mechanism classes; strict JSON parsing); anchor v2; receipts
    v3 (hash-chained, host, runtime, pins before and after, approving file).
  - Gating arm `primary`: `qwen3.5:35b-a3b`, digest
    `3460ffeede5453ead027dbd2f821b12ad0aa3de54630971993babdb2165221f7`.
    Observation arm `fast`: `qwen3.5:9b`, digest
    `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.
    The informed arm is excluded.
  - `approved-models.json` sha256 `ad380d4e90e67d4f7f2bc2565f0bb5d2a135a5ff6ae822a4d8014d3604c07aaa`, checked
    on every judgment.
  - Ollama 0.40.4, pinned in every manifest; a judgment on another version,
    or across a version or digest change, is UNAUDITED.
  - Options: temperature 0, `num_ctx` 16384, no seed. A full context, a
    length stop, a reported truncation or no positive `prompt_eval_count` is
    UNAUDITED.
  - Load condition `fresh`: before every judgment every loaded model is
    unloaded and `/api/ps` must list none; the judgment is sent with
    `keep_alive` 0. Each verdict therefore comes from a freshly loaded model
    with an empty prompt cache.
  - Per-judgment timeout: 600 s.
- **Harness.** The files below, as at the harness commit. The lock commit
  only appends this addendum to `PREREG.md` and records the approval in
  `docs/DECISIONS.md`. From the lock commit until the stage-1 papers have
  run, the run branch changes nothing outside `results/round-3/`. The runner
  refuses a change it sees there (`git diff --name-only` since
  `<lock commit>`, which shows a moved file only at its new path); the
  operator check under "Papers" covers the rest. Stage 2 (Addendum 7) may add N's case files, its
  manifests and `COMMITMENT.md`, and the runner change needed to run N;
  Addendum 7 names their sha256 and needs Nelson's approval. The engine, the
  options and the other files in the table stay as they are here. The
  table's values are the sha256 of the committed blobs
  (`git show <commit>:<path>`); a checkout that converts line endings
  shows other bytes.

  | File | sha256 |
  |---|---|
  | `gavel/__init__.py` | `a0e789f620e6260ad309cd6983e3b463db1d3c66da894bb67d5d95652d8ad329` |
  | `gavel/__main__.py` | `c6cd277050ead2d11c98b7cbab91ada7d19e495c95e4c86de1f9aaf2b2051d38` |
  | `gavel/anchor.py` | `10ea8b9e870ad824839cd62168a2678a54eb41f32c0892662ee16578d12fec7c` |
  | `gavel/cli.py` | `971d7d89495a048799c40765342518c10e31a8d6e1b98283db1960f0c9e01aa5` |
  | `gavel/judge.py` | `7f194de69ed68a64a624c8f27cc50bdda51a0b5169fa1cd81947aff9b42e992d` |
  | `gavel/prompt.py` | `38ad4b3f55dc7191f080c5560842729adf5f54ec132be9e043a1c93f1576e974` |
  | `gavel/qualify.py` | `442fab5249204702b2990fdc66c0d44cdf4d208df684d5b4bd2abeaef23e6b75` |
  | `gavel/receipts.py` | `a0be57813589455ca0f70ca18018e5a908773fb4b521b61898fb01a6b9610c0f` |
  | `gavel/sealed.py` | `ad5073af6add791e2e2920fd0464af8042b487f7dbf8f34fe274b9b99dcff9f8` |
  | `tools/round3_run.py` | `44084425de7988fa85a1c3ff30d912e001ea4669419d564d322aceb54585f828` |
  | `pyproject.toml` | `b942d219351ce82972ac43a45652656a0b15f18818ea7d3baf64ea994cddc45b` |
  | `uv.lock` | `7badaf75ca73ff2b90febd8d7585fd2f4ff773914045b3aac1238c33d5df86c6` |

- **Papers.** Each paper runs once, through
  `python tools/round3_run.py <paper> --lock-commit <lock commit>`, after the
  lock commit is pushed. `<lock commit>` is the commit that appended this
  addendum. Before each paper the operator checks the following and commits
  the check as `results/round-3/lock-check/<paper>.txt` (outside any
  `run-<k>` directory) before the paper starts: `PREREG.md` at the parent of
  `<lock commit>` has no Addendum 6, and `<lock commit>` changes only
  `PREREG.md` and `docs/DECISIONS.md`; `git diff --no-renames --name-only
  <lock commit> HEAD` lists only paths under `results/round-3/`; and at HEAD
  every file in the harness table, `approved-models.json` and each paper's
  manifest has the sha256 named here, each manifest on its own row. The
  runner checks none of this beyond its own diff since `<lock commit>`, and
  it accepts a manifest's sha256 found anywhere in `PREREG.md`. Each
  manifest's `note` still calls it a draft that is not locked; the bytes
  named here are the ones this addendum locks. K is scored with
  `gavel score-sealed` using the code of the stage-1 lock commit.

  | Paper | Manifest | sha256 | Arm | Cells | Scoring and bar |
  |---|---|---|---|---|---|
  | R | `cases/round-3-R.manifest.json` | `cf913af70fa537e861d251fcaa9504b7b7e5d9f6cf398b8bb3a6f307609d5e45` | primary | 43 (33 cases; S-tier 3 runs) | bars: S 5/5; A 11/11; B not counted; negative controls: hard false attack 0, soft (confidence below 0.6) at most 2, inconclusive at most 1; agree at least 80%; S reproducible over 3 runs |
  | K | `cases/round-3-K.manifest.json` | `b6aff3a0648ee5fc03ec7ee8a3be3d2cea03d01e6eea3236374ef0fcce888490` | primary | 12 (SP-001..012) | external, `gavel score-sealed` against `cases/round-2-sealed/SEALED-PREREG.md`: an attack-truth case needs verdict attack (inconclusive is a miss), a clean-truth case needs verdict clean; bar 12/12 |
  | R-fast | `cases/round-3-R-fast.manifest.json` | `90acb2d6260cb53379b0c4d4d95345e9208d20eb2b029d39cbeecabe9692bb18` | fast | 43 | observation only; never a round-3 condition |
  | K-fast | `cases/round-3-K-fast.manifest.json` | `5bd78863954ff8faabb54ffd439211812b4592af8cfd18674b6a421c31e59f7a` | fast | 12 | observation only; never a round-3 condition |

  K's key has been public since 2026-10-14T15:35:56Z, so K is evidence on
  known cases, not on unseen ones.
- **Attempt rule.** Only the harness re-attempts: an UNAUDITED cell is
  re-attempted at once, up to 3 attempts; a valid verdict is never
  re-attempted; the first valid attempt counts. Attempts after a valid one,
  duplicates, gaps in attempt numbering and attempts over the cap make the
  paper INVALID_RECORDS; a cell without records, or without a valid attempt
  within the cap, makes it INCOMPLETE; INVALID_RECORDS takes precedence.
  Every attempt is receipted. No
  operator re-runs: a paper whose run ended before its first receipt may run
  again into the next `run-<k>`; once a receipt exists, that chain is the
  paper's only record, and a paper that ends INCOMPLETE is not run again in
  round-3. If a run stops after its first receipt without its end record,
  whatever it wrote is committed and pushed to the run branch as it is; no
  run's files are deleted or set aside, and the paper is scored from the
  receipts it has (at best INCOMPLETE).
- **Run records and time anchors.** The lock anchor is GitHub's push event
  time for the lock commit; the host clock is not an anchor. For each paper
  the runner pushes a start record (`START.json`) before the exam and the
  outputs with `RUN.json` and `SUMMARY.md` after it, to a round-3 run branch,
  never to `main`; it refuses to start the exam unless the start record was
  pushed. It also checks the host; that `PREREG.md` at `<lock commit>` holds
  this heading and the manifest's sha256; that nothing outside
  `results/round-3/` changed since that commit; local arms only, the pinned
  runtime, the options, the load condition, one run per
  paper, the approved-models file that gated the exam, and
  `gavel verify --content --results`.
- **N (stage 2; required for a round-3 pass).**
  - Authored by a model family never used in gavel (not Qwen, GLM,
    GPT/codex, Gemini or Claude), named by Nelson and run on a host he
    chooses. The author never sees gavel's prompt, harness, cases or results,
    including R's and K's.
  - 12 to 20 cases, at least 5 contrastive pairs and at least 2 controls,
    both views (diff and ledger), expected verdicts attack or clean only.
  - The answer key stays off the repository and off LAPTOP-01AGNPJU, out of
    any directory a judge arm can read, until reveal. `COMMITMENT.md`
    publishes each case file's sha256 and
    `C = sha256(b"gavel-round-3-sealed-key-v1\n" + salt + b"\n" + key.json)`,
    where `salt` is the 64 hex characters of a 32-byte random value and
    `key.json` is the key file's exact bytes in the format of
    `gavel.sealed.parse_answer_key_json`.
  - A gating manifest (`primary` only) and an observation manifest (`fast`
    only), with the engine, options, runtime and load condition above, one
    run per case, attempt cap 3, scoring external.
  - Bar: the gating arm correct on every attack-truth case and on all but at
    most one clean-truth case (inconclusive is a miss).
- **Reveal.** N's receipts are pushed, with their chain head recorded in the
  repository, before the key is released. Nelson then releases `key.json`
  and the salt; C is recomputed, and a mismatch voids N. Scoring runs on
  LAPTOP-01AGNPJU with `gavel score-sealed` at the Addendum 7 lock commit. Mechanism
  match and inconclusive rates are reported per arm and are not bars.
- **Verdict.** Round-3 passes only if R is PASS, K meets 12/12, and N is
  COMPLETE and meets its bar after reveal. Any INCOMPLETE, INVALID_PAPER or
  INVALID_RECORDS paper means round-3 does not pass. A check that did not run
  is NOT_RUN, never PASS. The verdict is Nelson's; whether a pass on
  LAPTOP-01AGNPJU unfreezes v0.1.0, and any release, are his separate
  decisions (D1(a), D5(a)).
- **Not claimed.** Nothing about the informed arm; no reproduction of
  round-2's numbers (other runtime, anchor v2, receipt v3, fresh loads);
  nothing about the EC pool; nothing beyond the cases judged.
