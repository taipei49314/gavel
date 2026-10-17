# Round-3 PREREG: DRAFT (nothing here is locked)

- Status: **DRAFT**, written 2026-10-15 by the takeover agent on branch
  `fix/exam-validity`, and revised the same day on branch `docs/pju-venue`
  for the venue Nelson set: LAPTOP-01AGNPJU under EC POLICY
  `gavel-pju-execution` (docs/DECISIONS.md: 「round3 用pju」 at
  2026-10-15T09:48:43Z, authorized by
  「這個專案授權使用pju跑 因為所有資源都在pju」 at 09:49:47Z). Nothing in
  this file is locked, approved or in force. Every `<TO-LOCK>` value is
  decided at the lock.
- Revised on 2026-10-15 from 17:16Z (2026-10-16 +0800) on branch
  `round-3/prelock-smoke`, on Nelson's 「開始實驗 直接朝你規劃 你執行
  遇到重大決策問我」 and his answers of 17:23:48Z and 17:26:52Z
  (docs/DECISIONS.md, "2026-10-15 (round-3 preparation)"): Ollama's automatic
  updates turned off; completeness option (B) with `primary` as the gating
  arm; pushes for round-3 authorized; N deferred until a new model family or
  another computer is available. The pre-lock smoke run is done (section 2),
  the R and K manifests and the runner script are written (sections 2 and 5),
  and section 10 lists what is left for the lock.
- Revised on 2026-10-16 from 20:08Z on the same branch, on Nelson's
  「全部照建議」 (2026-10-16T20:08:01Z, docs/DECISIONS.md, "2026-10-16
  (round-3 lock items)"), which adopts the proposals of section 10: every
  judgment on a freshly loaded model (4a(i)), Ollama 0.40.4 with no seed, the
  K bar 12/12, the timeout 600 s, the runner's start and end pushes, and a
  two-stage lock. The harness change for 4a(i) is made and its smoke run is
  done (section 2). These are adopted proposals, not a lock: nothing here is
  locked until Nelson approves the final text (section 10, item 7).
- Lock procedure: Nelson approves the final text and the lock in his own words
  (recorded verbatim in docs/DECISIONS.md, as with Addendum 1's
  「人類開考前核可」); the approved text is then appended to `PREREG.md` as its
  next addendum and pushed before any round-3 judgment (section 8). PREREG.md
  stays append-only.
- Round-2 is not changed by anything here. Its status of record is INCOMPLETE
  on both papers (decision D1(a), adopted by Nelson on 2026-10-15), and every
  result produced on the work machine LAPTOP-01AGNPJU except the T-540
  session results Nelson accepted at 09:41:31Z, and the pre-lock smoke
  results he accepted at 2026-10-17T15:39:34Z, stays 「未驗收」; the standing
  authorization does not accept them retroactively. v0.1.0 stays frozen
  (Addendum 3: 「重考；PASS 前不發」; D1(a): until a round-3 run on the EC pool
  passes); whether a round-3 pass on LAPTOP-01AGNPJU unfreezes it is Nelson's
  decision, and any release needs his separate authorization (D5(a)).

## 0. Disclosure: this design is motivated by round-2's problems

This draft was written after round-2's results were known, and each rule
below answers a problem found in round-2 by the 2026-10-15 takeover audit
(finding ids in parentheses). None of these rules is applied to round-2.

| Round-2 problem | Round-3 rule |
|---|---|
| Four re-attempts (CW-A07 fast; SP-004 fast; SP-007 fast twice) that no addendum provided for, plus two calls that left no receipt; evaluation took the last record per cell (CR-01, R2-01, R2-03) | Harness-only attempt rule fixed before the run (section 4) |
| The re-attempts ran after Ollama had upgraded itself from 0.35.0 to 0.40.4 (03:37-03:38 +0800 on 2026-10-15) | Runtime pinned to 0.40.4 in every manifest and receipt; a judgment on any other version is UNAUDITED; freezing the host's automatic updates needs Nelson's separate OK (sections 1 and 2) |
| The expected judgment matrix was derived from the run itself (CR-10) | Locked manifests with case sha256s; evaluate reads the matrix from the manifest only (section 5) |
| The sealed answer key was public on GitHub from 2026-10-14T15:35:56Z, before the sealed run, and the informed arm ran an agent CLI in the repository's working directory (F3, CR-09) | Salted hash-only commitment; key off-repo and off the exam host LAPTOP-01AGNPJU until reveal; informed arm excluded (sections 3, 5 and 6) |
| Evidence text could close its own anchor block (ATK-009) (CR-04) | Anchor v2 (section 1) |
| The approved-models gate was not called on the exam path (CR-02, F4) | Checked on every judgment, before and after the call (section 1) |
| Receipts were not unique and did not bind run, time or host; raw output was dropped on UNAUDITED (R2-12, CR-06, CR-07, GOV-12) | Receipt v3, hash-chained, with host and runtime (section 1) |
| The context size was fixed and unrecorded; truncation could pass silently (CR-16) | num_ctx recorded; a full context or a length stop is UNAUDITED (section 1) |
| Tables were written by inline commands that were not committed (CR-03, R2-04) | Committed scoring code with its sha256 fixed at the lock (section 7) |
| Every round ran on a work machine (GOV-1, F1, R2-02) | Round-3 also runs on LAPTOP-01AGNPJU, but under Nelson's standing authorization recorded in EC before the run (POLICY `gavel-pju-execution`); every receipt records the host, and results are labelled "human-authorized local PJU, NOT EC pool" (section 2) |

## 1. Engine

| Part | Value |
|---|---|
| Prompt | v4, unchanged (`PROMPT_VERSION = 4`); instruction header sha256 `ac22bc746831a994d4b5f75cde5f678ea2f4bb16abe7114570d0a71fb87984e3` (as in the T-540 session's `round2/seed-1/versions.json`, and recomputed on 2026-10-15 at `d7ea7ace` with `workloads/gavel_verify/round2.py` `versions()`; confirmed again at the lock commit) |
| Verdict schema | v2 (attack, clean, inconclusive; four-part anatomy for attack), closed list of 11 mechanism classes, strict JSON parsing (CR-17) |
| Anchor | v2 (`ANCHOR_VERSION = 2`): `<<<GAVEL` inside evidence, in any ASCII letter case, gets a `!` appended (`<<<GAVEL!`, `<<<gavel!`); END markers repeat the block id and sha256. The parser accepts only what the renderer writes. Limit: Unicode look-alikes of the marker (fullwidth or Cyrillic characters, zero-width characters) are not escaped, so the guarantee that a block closes only at its own END marker holds for the parser and receipt verification, not for what the model may take for a marker. This changes the judge's input relative to round-2, which is why it needs a new round (PREREG procedure 3: 「揭曉後禁調 prompt／threshold；要改＝round 1、新 PREREG」) |
| Receipts | v3: receipt_id over the whole body, hash chain, host, Ollama version, pin before and after, the approved-models file that approved the pin (name and sha256), options, generation counts, raw output kept on UNAUDITED. `gavel evaluate` and `gavel score-sealed` re-render each receipt's locked case file and refuse a receipt whose anchor does not match it |
| Primary arm | `qwen3.5:35b-a3b`, manifest digest `3460ffeede5453ead027dbd2f821b12ad0aa3de54630971993babdb2165221f7` |
| Fast arm | `qwen3.5:9b`, manifest digest `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7` |
| Runtime | Ollama `0.40.4`, the version on LAPTOP-01AGNPJU (observed 2026-10-15 in the T-540 session, `/api/version`), pinned in every manifest (`runtime.ollama_version`). `gavel exam` refuses a paper at preflight when the daemon reports another version, and a judgment on any other version, or one whose version changes during the call, is UNAUDITED. This Ollama updates itself: its app logs on the host (`%LOCALAPPDATA%\Ollama\app*.log`, which go back to 2026-09-30) record two automatic upgrades, from 0.34.4 to 0.35.0 at 19:53-19:54 +0800 on 2026-10-01, and from 0.35.0 to 0.40.4 at 03:37-03:38 +0800 on 2026-10-15 (0.40.4 started at 03:38:00 +0800, 2026-10-14T19:38:00Z, as in `results/round-2/provenance/README.md`), the second between round-2's main run and its re-attempts. Freezing it for the round, so that it cannot update itself, is an Ollama configuration change and needed Nelson's separate OK (EC POLICY `gavel-pju-execution`). He gave it at 2026-10-15T17:23:48Z (「授權我關 (Recommended)」), and at 17:25:36Z the app setting `auto_update_enabled` was set from 1 to 0 and read back as 0 (docs/DECISIONS.md). The app restarted at 2026-10-16T14:00:11Z still on 0.40.4, and the setting read 0 at 19:38Z. From the restart to 2026-10-16T19:00Z its hourly checks logged that 0.40.5 is available, but never "update already downloaded", which the log recorded on 2026-10-14 before the last automatic upgrade (app.log; read-only checks on 2026-10-16). The preflight's version check stays the guard. An update started by hand from the Ollama tray would still change the runtime; the preflight would then refuse the paper. Round-2's main run used 0.35.0; going back to it would mean installing another Ollama version, which needs Nelson's separate OK; this draft does not propose it |
| Options | `temperature 0`, `num_ctx 16384`; no `seed` (adopted 2026-10-16T20:08:01Z), as in the pre-lock smoke runs, where temperature 0 gave byte-identical raw outputs over three runs of each case (section 2). A prompt that fills the context, a length stop, a reported truncation or a response without a positive `prompt_eval_count` is UNAUDITED. The guard trusts the daemon's count; the pre-lock smoke run measured that the pinned runtime reports the same count for a prompt run from an empty cache and for the same prompt run again from its cache (section 2) |
| Load condition | `fresh` in every manifest (`load_condition`; decision 4a(i), adopted 2026-10-16T20:08:01Z). Before each judgment the harness unloads every model the daemon lists and waits until `/api/ps` lists none, then sends the judgment with `keep_alive` 0, so every verdict comes from a freshly loaded model with an empty prompt cache and does not depend on the case judged before it. A model still listed after 120 s, or an unreadable `/api/ps`, makes the judgment UNAUDITED. Each receipt records the condition, `keep_alive` 0, what was loaded before the unload, the empty listing read just before the call, and the daemon's `load_duration`; `gavel verify --content` refuses a valid verdict recorded otherwise, and `gavel evaluate`/`score-sealed` refuse a local receipt of the paper judged without it |
| Approval check | approved-models.json at the repository root, checked on every judgment; the model digest and the Ollama version are read before and after each call and must not change. The file's name and sha256 are recorded in results.json and in every receipt the check passed, and they must be the lock commit's file (section 2) |
| Harness | gavel at the harness commit `<TO-LOCK: SHA>`, named when Nelson approves the stage-1 lock; the stage-1 candidate addendum (`docs/proposals/round-3-stage-1-addendum.md`) lists its files' sha256 |

If LAPTOP-01AGNPJU no longer holds either model at its approved digest, or the
pre-lock smoke run shows the pinned runtime cannot run them there, round-3 is
BLOCKED: a different digest is a different engine (SPEC §1: 「換模型＝換引擎」),
which needs Nelson's decision and requalification under its own lock, and
adding or removing a model needs his separate OK.

## 2. Venue

- LAPTOP-01AGNPJU, under Nelson's standing authorization EC POLICY
  `gavel-pju-execution` (EC task T-542; docs/DECISIONS.md,
  2026-10-15T09:49:47Z). Never LAPTOP-16NUA5I8. `hostname` is checked before
  any judgment, and every receipt records the host. Results are labelled
  "human-authorized local PJU, NOT EC pool" and are not EC pool evidence.
- Within that row: a virtual environment built from the committed `uv.lock`
  at the lock commit, and the judge run through the committed harness with
  the Ollama already on the host and the digests approved in
  approved-models.json. Outside it, each needing Nelson's separate OK:
  installing, upgrading or reconfiguring Ollama (freezing its automatic
  updates included, section 1), adding or removing models, and any agent CLI
  as a judge arm.
- No host preparation: the runtime and both models are already on the host.
  The EC pool workload drafts `judge-host-prepare`, `judge-smoke` and
  `gavel-exam` (`workloads/ec-workloads.drafts.json`) were written for a pool
  host and refuse to run on a work machine; they are not round-3's route.
- Precondition for the lock: a smoke run on LAPTOP-01AGNPJU, through the
  committed harness on the pinned runtime, measuring what the `judge-smoke`
  draft describes (the three synthetic smoke cases, primary arm, three runs
  each; never exam material). Its timings fix the per-judgment timeout and
  each paper's expected run time; a paper is never resumed. It also records
  `prompt_eval_count` over the three runs of each case and fails if a later
  run reports a different count than run 1 (a cached prompt counted short
  would blind the truncation guard); if it does, the lock needs a remedy (for
  example a check that does not rely on the daemon's count) before any paper
  runs.
- **Done on 2026-10-15** (`results/round-3/prelock-smoke/README.md`; label
  "human-authorized local PJU, NOT EC pool"; Nelson accepted the results at
  2026-10-17T15:39:34Z). Four sessions, each judging the three smoke cases three times:
  primary and fast with each case's first run on a freshly loaded model, and
  two further fast sessions to explain a difference.
  - All 36 judgments were valid. Every case gave the same output in its three
    runs. There were no length stops; the minimum headroom was 14801 tokens.
  - `prompt_eval_count` was the same for a prompt run from an empty cache and
    for the same prompt run again from its cache, so the truncation guard can
    rely on it.
  - Primary reproduced the T-540 smoke outputs byte for byte. Seconds per
    judgment: primary 50 to 87, fast 40 to 138; a model reload took up to
    35 s. A generation that fills `num_ctx` (about 15,000 tokens) would take
    about 450 s at the slowest measured primary rate. Timeout: 600 s
    (gavel's default and round-2's value; adopted 2026-10-16T20:08:01Z).
  - **Finding: the fast arm's output for a case depends on the case judged
    before it on the same loaded model.** The cause is the reuse of a cached
    prefix of the previous prompt (the shared instruction header). On a
    freshly loaded model, SMOKE-NEG-1 (a negative control) was judged
    attack. Judged after SMOKE-ATK-2 on the same model, as in T-540, it was
    judged clean. Each condition reproduced in two sessions.
  - The primary arm gave the same outputs under both conditions, but only
    three cases were tried. Nelson adopted 4a(i) at 2026-10-16T20:08:01Z:
    round-3 judges every case on a freshly loaded model (section 1, "Load
    condition"). `tools/round3_run.py` also unloads every model before a
    paper and keeps the load conditions with the run.
- **Fresh-load smoke run on 2026-10-16** (`results/round-3/prelock-smoke/fresh/`,
  at `3dd5329d`; same label; accepted at 2026-10-17T15:39:34Z). The three
  smoke cases, three runs each, on both arms, every judgment under load
  condition `fresh`.
  - All 18 judgments were valid, and each recorded `fresh`, `keep_alive` 0
    and an empty `/api/ps` listing before the call; the Ollama server log
    shows one model start per judgment. Every case gave the same output in
    its three runs, `prompt_eval_count` was the same in every run, there
    were no length stops, and the minimum headroom was 14801 tokens.
  - Every output equals the earlier fresh-model output for its case and arm.
    SMOKE-NEG-1 was judged right after SMOKE-ATK-2, the order that had given
    the fast arm's clean verdict, and the fast arm gave the fresh-model
    output (attack, a hard false attack on that negative control), so the
    order dependence is gone. Primary was unchanged (clean).
  - Seconds per judgment, load included: primary 59 to 83 (load 19 to 22),
    fast 52 to 131 (load 3 to 5). Expected run time: R and R-fast 43 cells
    each, K and K-fast 12 each; at these rates R takes about 40 to 60
    minutes and all four papers about 1.7 to 3.3 hours, plus any
    re-attempts.
- The checks the `gavel-exam` draft made around `gavel exam` still apply:
  every arm in a paper's manifest uses the local transport `ollama`; the
  manifest pins the Ollama version and fixes the options; results.json and
  every receipt that passed the approval check record the lock commit's
  approved-models.json sha256; `gavel verify --content --results` passes on
  the paper's output; and each paper runs once (section 4). They are
  enforced on this host by the committed runner script
  `tools/round3_run.py`, adapted from `workloads/gavel_exam/run.py` without
  its pool-host checks (adopted 2026-10-16T20:08:01Z); it also refuses a
  manifest that does not set `load_condition` `fresh`.

## 3. Arms

- Gating arm: `primary`. The gating arm must use the local Ollama transport
  (validate_manifest refuses anything else). Nelson chose option (B) below at
  2026-10-15T17:23:48Z on a question that proposed `primary` as the gating
  arm.
- Fast arm: recorded, in its own observation papers (option (B)).
- Informed arm (agy): **excluded**. The agy transport now runs in an empty
  temporary directory with no shell, but that is not a sandbox: agy's own tool
  and file-access settings are not verified (CR-09). EC POLICY
  `gavel-pju-execution` does not cover an agent CLI as a judge arm. It may
  join a later round only after a sandboxed transport is verified and Nelson
  separately approves it as a judge arm; it is never run on a sealed paper
  before reveal.
- Completeness (this choice is motivated by round-2's fast-arm gaps and is
  disclosed as such):
  - (A) every arm listed in a paper's manifest gates that paper's
    completeness (the current harness behaviour);
  - **(B), chosen by Nelson at 2026-10-15T17:23:48Z** (「(B) 只看 primary
    (Recommended)」): a paper's manifest lists only the gating arm; the fast
    arm runs as a separate observation manifest over the same cases, whose
    status is reported but does not block the paper. Each paper (R, K, and N
    when it exists) therefore has a gating manifest with `primary` as its only
    arm and an observation manifest with `fast` as its only arm (and so as
    that manifest's own `gating_arm`, which the format requires). An
    observation paper's status, PASS or not, is never a round-3 condition.

## 4. Attempt rule

- Attempts are made by the harness only: `gavel exam` (run_paper) re-attempts
  a cell immediately when its attempt is UNAUDITED, up to an attempt cap of
  **3**.
- Only UNAUDITED cells are re-attempted. A valid verdict is never re-attempted,
  whatever it says.
- The first valid attempt counts. Attempts after a valid one, duplicate
  attempts, gaps in attempt numbering and attempts over the cap make the paper
  INVALID_RECORDS.
- Every attempt is receipted in one hash-chained v3 receipts file per paper;
  results.json records the chain head and count, and `gavel verify --content
  --results` checks them. Every re-attempted cell is listed in the report.
- No operator re-runs. Each paper is run once. On a pool host the dispatch
  record (EC ledger row and private receipt ref) would have enforced that; on
  LAPTOP-01AGNPJU the run record is made by the runner script
  `tools/round3_run.py` (section 2; adopted 2026-10-16T20:08:01Z), which
  commits and pushes a start record
  (`results/round-3/<paper>/run-<k>/START.json`: paper, manifest and its
  sha256, lock commit, runner sha256, host, output directory) before the
  exam, and the exam's outputs with an end record (`RUN.json`, `SUMMARY.md`)
  when it ends. Nelson authorized these pushes for round-3 at
  2026-10-15T17:23:48Z (「整個 round-3 授權 (Recommended)」, AGENTS.md
  rule 9). `gavel exam` only refuses an output directory that already holds a
  run, and creates results.json first as a "started" marker, so a run that
  stops part-way is visible. If a run ends before its first receipt (the
  preflight refused, or the daemon was unavailable), nothing was judged and
  the same paper may be run again, into the next `run-<k>`. Once any receipt
  exists, that chain is the paper's only record: the runner refuses the paper
  from then on, and a paper that ends without resolving every cell is
  INCOMPLETE and is not run again in round-3.
- The runtime stays fixed for the round; a version or digest change during a
  judgment makes it UNAUDITED.

## 5. Papers

Each paper is a locked manifest in the format of
`gavel.qualify.validate_manifest`: case ids, paths, sha256, tier, role; arms
and runs; gating arm; attempt cap 3; options; runtime; scoring; bars.
Completeness comes first: a missing or unresolved cell makes the paper
INCOMPLETE, and an INCOMPLETE paper is never scored (Addendum 4:
「缺件/UNAUDITED/題數漂移 → INCOMPLETE，永不計分」).

### R: regression (scoring "bars")

- The 33 round-2 regression cases, unchanged (case sha256 as listed in
  `workloads/gavel_verify/round2_papers.json`). Census S5, A11, B6, negative 6,
  agree 5.
- Gating arm 3 runs on S-tier cases, 1 run otherwise: 43 cells.
- Bars as Addendum 5: S 5/5; A 11/11; B uncounted (calibration); negative
  controls: hard false attack 0, soft (confidence below 0.6) at most 2,
  inconclusive at most 1; agree at least 80%; S reproducibility over 3 runs.
- Manifest draft: `cases/round-3-R.manifest.json` (paper `round-3-R`), with
  case paths into `cases/round-2-regression/`, `primary` only, attempt cap 3,
  the options and runtime of section 1, no seed, and `load_condition`
  `fresh`. Observation paper:
  `cases/round-3-R-fast.manifest.json` (`round-3-R-fast`), the same cases,
  runs and bars with `fast` as its only arm.

### K: known sealed cases (scoring "external")

- SP-001..012 from round-2's sealed paper. Their key has been public since
  2026-10-14T15:35:56Z (F3), so they count as known cases, not as unseen-case
  evidence.
- Their case files carry tier null, which the bar scorer cannot score, and
  changing them would change locked case bytes. So they form their own
  manifest, scored with `gavel score-sealed` against
  `cases/round-2-sealed/SEALED-PREREG.md` (the Addendum 5 rule: an
  attack-truth case needs verdict attack, inconclusive is a miss; a clean-truth
  case needs verdict clean).
- Bar: the gating arm correct on 12/12 (adopted 2026-10-16T20:08:01Z).
- Manifest draft: `cases/round-3-K.manifest.json` (paper `round-3-K`), with
  case paths into `cases/round-2-sealed/`, `primary` only, one run per case,
  attempt cap 3, scoring "external", `load_condition` `fresh`. Observation paper:
  `cases/round-3-K-fast.manifest.json` (`round-3-K-fast`), with `fast` only.

### N: new sealed paper (scoring "external"), required

- **Deferred.** Asked at 2026-10-15T17:23:48Z which family should author N, Nelson
  answered 「目前資源就這樣了」; asked how to proceed, he chose 「等有資源再說」
  at 17:26:52Z: R, K and the lock packet are prepared now, and N waits until
  a new model family or another computer is available. The two unused
  families found on LAPTOP-01AGNPJU (the grok CLI, xAI; the MiMo desktop app,
  Xiaomi) were not used, because authoring there conflicts with the key rule
  below and is outside EC POLICY `gavel-pju-execution`. N is still required
  for a round-3 pass. Under the two-stage lock adopted on 2026-10-16T20:08:01Z
  (section 10), R and K run after stage 1, before N exists; N's cases are
  locked in stage 2.
- Authored for round-3 by a model family never used in gavel. Families already
  used: Qwen (the judge arms); GLM (the previous builder; PREREG.md records
  the author of the 2026-10-01 red-team fixtures as 「疑似 GLM 系 agent」);
  GPT/codex (`gpt-6.1-sol`: attack round-1 wave 1 and the round-2 sealed
  paper); Gemini (the informed arm); Claude (this takeover, the harness fixes
  and this draft). Nelson
  names the family and launches the authoring session on a host he chooses,
  with the brief kept outside the repository. Writing the sealed paper with
  an agent CLI or model on LAPTOP-01AGNPJU is outside EC POLICY
  `gavel-pju-execution` and needs Nelson's separate OK.
- The author never sees gavel's prompt, harness, cases or results.
- Size rule `<TO-LOCK>` (stage 1); proposal: 12 to 20 cases, at least 5
  contrastive pairs and at least 2 controls, both views (diff and ledger),
  expected verdicts attack or clean only. The exact count is fixed with N's
  cases at stage 2, within this rule.
- Case files are committed at the lock with their sha256 in the manifest. The
  answer key stays off-repo, with Nelson, until reveal: never in the
  repository, never on LAPTOP-01AGNPJU (the exam host, including the gavel
  checkout), never in any arm's working directory, and never in any directory
  a judge arm can read, before reveal.
- Commitment (salted, so that a short key cannot be found by trying every
  combination): `COMMITMENT.md` publishes each case file's sha256 and
  `C = sha256(b"gavel-round-3-sealed-key-v1\n" + salt + b"\n" + key.json)`,
  where `salt` is the 64 hex characters of a 32-byte random value and
  `key.json` is the answer key file's exact bytes in the format of
  `gavel.sealed.parse_answer_key_json`. At reveal Nelson releases `key.json`
  and the salt; anyone can recompute C.
- Bar `<TO-LOCK>` (stage 1); proposal: the gating arm correct on every
  attack-truth case and on all but at most one clean-truth case. The earlier
  draft added "at least `<p>` of `<P>` pairs discriminated" with no value
  proposed. That clause adds nothing to this bar: a pair is missed only when
  its attack case or its clean case is judged wrong, so a paper that meets
  the bar misses at most one pair. The proposal drops it.

### Round-3 verdict

Round-3 passes only if R is PASS, K meets its bar, and N is COMPLETE and meets
its bar after reveal. Any INCOMPLETE, INVALID_PAPER or INVALID_RECORDS paper
means round-3 does not pass. A check that did not run is NOT_RUN, never PASS.
The verdict and any v0.1.0 release are Nelson's.

## 6. Reveal

1. N's receipts are pushed to GitHub (with Nelson's OK, AGENTS.md rule 9),
   with their chain head recorded in the repository, before the key is
   released (on a pool host they would have gone to the EC private receipt
   ref).
2. Nelson releases `key.json` and the salt. C is recomputed; a mismatch voids
   N.
3. Scoring runs on LAPTOP-01AGNPJU under EC POLICY `gavel-pju-execution`
   (section 7). Mechanism match and inconclusive rates are reported per arm
   (CR-18, R2-11); they are not bars unless the lock says so.

## 7. Scoring code

- R: `gavel.qualify.evaluate`, through `gavel exam`; report.json.
- K and N: `gavel score-sealed --manifest --key --receipts --out`
  (gavel/sealed.py), only on a COMPLETE paper; outputs written once; every
  table cell and summary line computed (Addendum 4:
  「對帳表一律由腳本生成（tools/tally_attack.py 慣例），禁手工彙寫」).
- Scoring runs on LAPTOP-01AGNPJU under EC POLICY `gavel-pju-execution`, at
  the lock commit in a virtual environment built from `uv.lock`; its outputs
  reach the repository by PR (pushes need Nelson's OK, AGENTS.md rule 9).
- Paths and sha256 at the harness commit: listed in the stage-1 candidate
  addendum, `docs/proposals/round-3-stage-1-addendum.md` (the `gavel`
  package, `tools/round3_run.py`, `pyproject.toml` and `uv.lock`).

## 8. Time anchors

1. The lock commit (the PREREG addendum, the manifests, COMMITMENT.md,
   approved-models.json and the harness) is pushed to GitHub before any
   round-3 judgment. GitHub's server-side push event time is the lock anchor;
   the host clock is not.
2. Nelson approves the lock (the lock text, the manifests, COMMITMENT.md, the
   harness commit and the runner script's sha256) before the first round-3
   judgment.
3. Each paper runs on LAPTOP-01AGNPJU after the lock anchor. Its receipts
   carry that host's clock, which is not a server-side time. A paper's start
   and end are anchored by the pushes of the run record in section 4, made by
   `tools/round3_run.py`, whose GitHub push event times bound each paper's
   run from both sides; the runner refuses to start the exam unless the start
   record was pushed (adopted 2026-10-16T20:08:01Z).
4. Reveal follows the publication of N's receipts (section 6).

## 9. What round-3 will not claim

- Nothing about the informed arm.
- No reproduction of round-2's numbers: round-3 runs on the same host, but on
  Ollama 0.40.4 (round-2's main run used 0.35.0), with anchor v2 and receipt
  v3, so its verdicts are not expected to match round-2's receipts byte for
  byte.
- Nothing about the EC pool: results are labelled "human-authorized local
  PJU, NOT EC pool", and no other host is claimed to reproduce them.
- No claim beyond the cases judged; the sealed sample stays small.

## 10. Decisions left for the lock (Nelson)

Settled since the first draft:

- Venue: LAPTOP-01AGNPJU (「round3 用pju」, 2026-10-15T09:48:43Z).
- Ollama's automatic updates: turned off with his OK (2026-10-15T17:23:48Z;
  section 1).
- Gating arm `primary`, completeness option (B) (17:23:48Z; section 3).
- Pushes for round-3, the run records included (17:23:48Z; section 4).
- The pre-lock smoke run is done (section 2). On the pinned runtime
  `prompt_eval_count` does not depend on the prompt cache, so the truncation
  guard can rely on it.
- Adopted on 2026-10-16T20:08:01Z with 「全部照建議」 (docs/DECISIONS.md),
  the proposals this section made:
  - 1: the runtime pin Ollama 0.40.4 (as recorded by the committed harness
    in the receipts of the pre-lock smoke runs), and no seed (section 1).
  - 3: the K bar, the gating arm correct on 12/12 (section 5).
  - 4: the per-judgment timeout, 600 s (section 2).
  - 4a: (i), every judgment on a freshly loaded model with an empty prompt
    cache, so that a verdict depends only on its case (section 1, "Load
    condition"). The harness change is made and its smoke run is done
    (section 2). Each primary judgment then includes a model load of 19 to
    22 s (fresh smoke run, section 2), about 14 minutes of load over R's 43
    cells; the measured time per judgment rose less, by about 6 s on average
    against warm judgments of the same cases. The alternative it replaces, cases judged one after another
    on one loaded model as in round-2, would have been reproducible only in
    the manifest's case order from an empty start.
  - 5: `tools/round3_run.py` enforces the `gavel-exam` checks and the
    one-run-per-paper record on LAPTOP-01AGNPJU, and its start and end
    pushes anchor each paper's run in time (sections 2, 4 and 8).
  - 6: a two-stage lock. Stage 1 locks everything except N's cases (this
    text, the R and K manifests and their observation manifests, N's bar and
    size rule, the options, the timeout, the harness commit and the runner),
    and R and K run after it. Stage 2, when N exists, locks N's case files,
    its manifests and COMMITMENT.md as a second addendum, under the rules
    fixed in stage 1. Round-3 still passes only with N (section 5). R and K
    results are therefore public before N is written; N's author must not
    see gavel's prompt, harness, cases or results (section 5). The takeover
    report that this answer approved named this item without restating the
    proposal; Nelson can overrule it when he approves the stage-1 text.

Left for the lock:

- 2, N: its author's model family, once a family and a computer are available
  (deferred at 2026-10-15T17:26:52Z, 「等有資源再說」); at stage 1, N's size
  rule and bar (section 5; proposals: 12 to 20 cases with at least 5 pairs
  and 2 controls; every attack-truth case and all but at most one
  clean-truth case correct).
- 7, approval of the stage-1 lock: the final text, the R and K manifests and
  their observation manifests, the harness commit, and the runner script's
  path and sha256 (in place of the `gavel-exam` entry sha256). The candidate
  is `docs/proposals/round-3-stage-1-addendum.md`: a short normative
  addendum with every hash filled in. The runner already has
  `JUDGMENT_TIMEOUT_S` 600 and, in place of its DRAFT refusal, refuses every
  paper until `PREREG.md` at the lock commit holds that addendum's heading
  and names the paper's manifest sha256; so nothing runs before the
  approved text is appended. At stage 2, approval of N's manifests and
  COMMITMENT.md.

Not lock decisions, settled on 2026-10-17T15:39:34Z (docs/DECISIONS.md): the
pre-lock smoke results are accepted (「接受」); v0.1.0 is not released
(「不發」); Ollama's automatic updates may be turned back on after round-3
(「跑完後可打開」; read as after N too). Still open: whether a later round-3
pass on LAPTOP-01AGNPJU unfreezes v0.1.0 (D1(a) names a round-3 run on the
EC pool).
