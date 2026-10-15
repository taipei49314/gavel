# SPEC clarifications: proposal (spec 0)

- Status: proposal, 2026-10-15, branch `fix/exam-validity`. SPEC.md itself is
  not changed by this file.
- Authority: SPEC.md's header says 「spec 修訂由 agent 提案；重大版本（號升級）由人類點名（pinwash 慣例）」.
  The agent proposes; Nelson decides whether to adopt each item and names any
  major version.
- Three kinds of item below:
  - **conformance**: the code at d0cb1dc did not do what spec 0 already says;
    this branch fixes the code and SPEC.md needs at most a clarifying note;
  - **correction**: SPEC.md states something that is not true of the code or
    the venue; the text needs a correction note;
  - **spec-1 candidate**: a real change of the specification, for Nelson to
    name or decline.
- When SPEC.md is edited (plan step J4, after a Nelson-named pool host has run
  judge-smoke), existing Chinese text is not rewritten: a false or stale
  statement is struck through with `~~...~~` and followed by an English
  correction note.
- Venue: this file was written under D2(A) (EC pool only). Later on
  2026-10-15 Nelson authorized gavel to run on LAPTOP-01AGNPJU (EC POLICY
  `gavel-pju-execution`, docs/DECISIONS.md), which supersedes the venue part
  of D2(A) for gavel. §1 below is revised for it (2026-10-15, branch
  `docs/pju-venue`); the other mentions of the pool in this file (the J4 note
  above, §4, §6 and spec-1 candidate 3) date from before it.

## §1 Judge identity: correction

Current text: 「正裁判：Ollama `qwen3.5:35b-a3b`；快臂：`qwen3.5:9b`（釘版主機：LAPTOP-01AGNPJU，12 GB VRAM）」,
「釘版五件套入每張收據：模型 tag、模型檔 sha256、prompt 全文 hash、temperature=0、verdict schema 版本」
and 「語意：**模型檔 sha256 屬於引擎版本的一部分**；換模型＝換引擎＝spec 版本檢討」.

Facts:

- LAPTOP-01AGNPJU is a work machine. EC POLICY work-machine-local forbids
  engine load on work machines, and results produced there since 2026-09-22
  are 「未驗收」 unless Nelson accepts them. Nelson first chose on 2026-10-15
  (D2(A)) that tests and the judge run only on the EC pool, the judge on a
  pool host he names. Later the same day (09:49:47Z) he authorized gavel to
  run on LAPTOP-01AGNPJU, recorded as the standing EC POLICY row
  `gavel-pju-execution` (T-542): gavel's tests, verification and judge runs
  through the committed harness, with the host's existing Ollama and the
  approved digests, until he revokes it. That supersedes the venue part of
  D2(A) for gavel. Results from there are labelled "human-authorized local
  PJU, NOT EC pool"; the round-0, round-1, M4 wave-1 and round-2 results stay
  「未驗收」.
- The digest gavel pins and checks is the Ollama manifest digest that
  `/api/tags` reports (approved-models.json `manifest_digest`), not a model
  file (GGUF) sha256.
- At d0cb1dc the Ollama runtime version and the context size were not
  recorded (CR-16), and round-2's main run and its re-attempts ran on
  different Ollama versions (0.35.0, then 0.40.4 after an automatic upgrade).

**Superseded proposal.** The proposal below was made under D2(A). It removed
the LAPTOP-01AGNPJU pin and made a Nelson-named EC pool host part of the
judge's identity. EC POLICY `gavel-pju-execution` superseded it on
2026-10-15; it is kept here for the record and is not proposed any more.

> ~~The judge's identity is: the model tags and their Ollama manifest digests
> as listed in approved-models.json; the Ollama runtime version, pinned per
> exam round; the generation options (temperature 0, num_ctx, seed if set);
> the prompt version with the sha256 of its instruction header, the anchor
> version and the verdict schema version; and the EC pool host named by
> Nelson on which the judge runs. Every receipt records all of them, the
> digest and runtime version read before and after the judgment, and the
> host. A different digest is a different engine (換模型＝換引擎). A different
> host or runtime version is recorded and needs a new round to qualify. The
> LAPTOP-01AGNPJU pin is removed.~~

**Proposed §1 text**, in substance, replacing it:

> The judge's identity is: the model tags and their Ollama manifest digests
> as listed in approved-models.json; the Ollama runtime version, pinned per
> exam round; the generation options (temperature 0, num_ctx, seed if set);
> and the prompt version with the sha256 of its instruction header, the
> anchor version and the verdict schema version. The pinned host stays
> LAPTOP-01AGNPJU, where gavel runs under EC POLICY `gavel-pju-execution`.
> Every receipt records the host, the Ollama version and the model digests,
> with the digest and runtime version read before and after the judgment. A
> different digest is a different engine (換模型＝換引擎). A different host or
> runtime version is recorded and needs a new round to qualify.

Already implemented for receipt v3 (PR #2, branch `fix/exam-validity`,
merged in `d97dbcd`): receipt v3 records host, transport and Ollama version,
the pin before and after each call, options and generation counts, and the
name and sha256 of the approved-models file that approved the pin (also in
results.json); judge_case checks approved models on every judgment and
refuses a changed digest or version.

## §4 Receipts and replay: correction

Current text: 「append-only JSONL；`gavel receipt verify` 離線重放（同輸入重跑，verdict 逐字一致）」.
README.md says 「離線可重放」.

Facts: there is no `receipt` subcommand, and nothing in gavel re-runs a model
to reproduce a receipt. `gavel verify` checks receipts offline without a
model: structure, the v3 hash chain and receipt ids, with `--content` the
embedded prompt and anchor texts and a re-parse of the raw output, and with
`--results` or `--expect-head` / `--expect-count` a cut or extended tail.
`gavel evaluate` and `gavel score-sealed` also re-render each receipt's
locked case file and require the receipt's anchor to match it, so a receipt
that judged other evidence is refused. None of this re-runs the model.
PREREG Addendum 4 already called replay 「獨立功能，另令執行」.

Proposed note: replay is **not implemented**. `gavel verify` is offline
verification, not replay. Replay would re-run the judge, which is engine load
and runs only on the EC pool; it is a spec-1 candidate (below).

## §5 Fail-closed exit codes: conformance

Current text: 「exit code：**0**＝clean（雙臂一致且無 findings）、**1**＝有 findings、**2**＝UNAUDITED。」
and 「任何 UNAUDITED 永不映射 exit 0。」

At d0cb1dc, `scan` returned 0 for verdict inconclusive and for an arm
disagreement of clean against inconclusive (CR-05). Spec 0 gives 0 only to a
clean result on which both local arms agree, and §6 says the informed arm's
result 「只入帳、不覆寫本地 verdict」, so this branch maps:

| exit | scan result |
|---|---|
| 0 | primary and fast both ran and returned valid clean verdicts (so they agree) |
| 1 | primary or fast returned attack or inconclusive, or the two disagree |
| 2 | any arm without a valid verdict (an opt-in arm included, see below), a required arm not selected, or input that cannot be judged; UNAUDITED wins over findings |

A valid verdict of an opt-in arm (informed) never changes the code: it is
printed, receipted and listed in the reasons as `recorded only:
informed=<verdict>`. `tools/tally_attack.py` follows the same rule for
"gate released".

This needs no spec change; SPEC.md can carry it as a clarifying note. The
UNAUDITED conditions listed in §5 are also made concrete on this branch:
daemon and transport errors (CR-14), a full context, a length stop, a
reported truncation or a response without a positive prompt_eval_count
(CR-16), a model digest or Ollama version that changes during a judgment, a
missing or malformed approved-models.json, and input JSON with duplicate keys
or NaN/Infinity.

One reading is left for Nelson. §5 says 「任何 UNAUDITED 永不映射 exit 0」 and
§6 says the informed arm's result 「只入帳、不覆寫本地 verdict」. For an opt-in
arm that ends UNAUDITED while primary and fast agree on clean, the two lines
point to different codes: 2 under §5, 0 under §6. This branch takes the
fail-closed reading and exits 2, and lists the question as spec-1 candidate 6
below.

The new commands have their own codes: `exam` and `evaluate` give 0 PASS,
1 FAIL, 2 not scored (INVALID_PAPER, INVALID_RECORDS, INCOMPLETE or refused)
and 3 COMPLETE (external scoring, not a pass); `score-sealed` gives 0 scored
and 2 not scored or refused. Any unexpected error exits 2.

## §6 Informed arm: conformance and correction

Current text: 「本地雙臂必跑；verdict 分歧本身入帳為 finding（calibration 訊號）」 and
「雲端 informed 臂＝opt-in，CLI subprocess（首選 codex `gpt-6.1-sol`），結果只入帳、不覆寫本地 verdict」.

Facts: at d0cb1dc the exam ran three arms including informed by default, and
`scan --arms informed` sent the informed arm to Ollama (CR-14). Round-2's
informed arm was gemini-4-argon-high through the agy CLI, not codex;
approved-models.json records the instruction as
「找antigravity cli , 找到gemini4 argon , 列入重考」.

Conformance on this branch: `scan` and `pin` default to primary and fast; the
informed arm runs only when selected and goes to the agy transport. Its valid
verdict is recorded only and does not change the scan exit code
(「結果只入帳、不覆寫本地 verdict」); its UNAUDITED exits 2 (the §5 reading
above). Exam papers list their arms in the locked manifest, and the gating
arm must be local.

An earlier commit on this branch (2ee6e88) let the informed arm make a scan
result stricter (an informed attack, inconclusive or disagreement gave 1).
That was a change to §6, not conformance with it. The commit "fix/exam-validity:
apply static review fixes" replaces it with the rule above, on this branch,
before any of it is published.

Proposed correction note: the informed arm named in §6 is stale; whichever
cloud arm is used is the one listed in approved-models.json for that round,
and it is recorded with its transport version. The round-3 draft excludes the
informed arm until a sandboxed transport is verified on the pool
(docs/proposals/round-3-PREREG-DRAFT.md, section 3).

## Spec-1 candidates for Nelson to name

1. **The fast arm's role in scan.** Spec 0 (§6 「本地雙臂必跑」, §5 0 only
   when 「雙臂一致」) makes the fast arm required, so any UNAUDITED fast
   judgment makes `scan` exit 2. In round-2 (results 「未驗收」) the fast arm
   had UNAUDITED first attempts on CW-A07, SP-004 and SP-007. Options: keep it
   required; make it recorded only, with the exit code set by the primary arm
   and a fast divergence or failure reported as a finding; or drop it from
   scan.
2. **Whether inconclusive keeps exit 1 for good.** Spec 0 already implies it
   (0 is clean only). A spec-1 alternative is a separate exit code for
   inconclusive; the conformance fix above does not depend on that choice.
3. **Replay** as a pool-only command that re-runs a receipt's judgment on the
   pinned engine and compares the verdict.
4. **Schema tolerance for recorded arms**, which round-2's REPORT listed as
   「spec 1 候選：recorded 臂的 schema 寬容/降級策略」.
5. **Identity and sandboxing of a cloud arm**, if one is reinstated: model id,
   transport executable hash and a sandbox requirement before it may judge
   any exam paper.
6. **An opt-in arm that ends UNAUDITED in scan.** §5
   「任何 UNAUDITED 永不映射 exit 0」 and §6
   「結果只入帳、不覆寫本地 verdict」 give different codes when primary and fast
   agree on clean. This branch exits 2 (fail-closed). Options: keep 2; or
   read §6 as covering the opt-in arm's UNAUDITED too, so the scan exits 0
   and the UNAUDITED opt-in result is only recorded.
7. **Whether an opt-in arm may ever make scan stricter** (an informed attack
   giving exit 1). Spec 0 does not allow it (§6 above); it would need a
   spec-1 change named by Nelson.
