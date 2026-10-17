# Round-3 pre-lock smoke run (2026-10-15)

**Label: human-authorized local PJU, NOT EC pool.** This is not an exam. It
used only the three synthetic smoke cases (`smoke/SMOKE-*.json`), never exam
material. It qualifies no judge, and its results await Nelson's acceptance.

- **Authority:** EC POLICY `gavel-pju-execution` (T-542), which covers smoke
  runs. Nelson's message at 2026-10-15T17:16:15Z: 「開始實驗 直接朝你規劃 你執行
  遇到重大決策問我」 (docs/DECISIONS.md).
- **Purpose:** the precondition for the round-3 lock in
  `docs/proposals/round-3-PREREG-DRAFT.md`, section 2. It gives the timings
  for the per-judgment timeout, and it shows whether the pinned runtime's
  `prompt_eval_count` can be trusted.
- **Host and runtime:** LAPTOP-01AGNPJU, with every receipt recording the
  host. Ollama 0.40.4 before and after each session, with nothing installed,
  upgraded or restarted. Digests: `qwen3.5:35b-a3b` `3460ffee…21f7` and
  `qwen3.5:9b` `6488c96f…3ea7`. approved-models.json sha256 `ad380d4e…7aaa`.
  Options: temperature 0, `num_ctx` 16384, no seed.
- **Path:** `workloads/judge_smoke/smoke.py`, through
  `gavel.qualify.judge_case`, with v3 receipts and no re-attempts. The
  virtual environment was built from `uv.lock`
  (`uv sync --frozen --no-python-downloads`).

## Sessions

| Directory | Commit | When (UTC) | Arm | Load condition | Tests before |
|---|---|---|---|---|---|
| `primary/` | `d7ea7ace` | 17:21:28–17:32:39 | primary | `--cold-first`: each case's run 1 on a freshly loaded model | 445 passed (`02-pytest.*`) |
| `fast/` | `d7ea7ace` | 17:32:39–17:45:14 | fast | `--cold-first` | (same session) |
| `fast-coload/` | `4b92355f` | 17:47:51–17:57:21 | fast | all models unloaded, then `--co-load qwen3.5:35b-a3b`; the three cases run one after another on one loaded model | 459 passed |
| `fast-alone/` | `4b92355f` | 17:58:40–18:11:05 | fast | all models unloaded, then `--cold-first` | 459 passed |

The `--co-load` in `fast-coload/` did not hold: Ollama evicted
`qwen3.5:35b-a3b` when `qwen3.5:9b` loaded, before the first judgment
(`fast-coload/smoke.json`: every judgment's `loaded` lists only
`qwen3.5:9b`; `fast-coload.session/session.txt`: 'loaded after' lists only
the 9b; found in the 2026-10-17 review). The session's finding does not
depend on it: its cases ran one after another on one loaded model.

Each session ran three runs of each case. `session.txt` (and
`*.session/session.txt`) hold the session logs. `attempt-1-not-run/` is a
first attempt at 17:20:43Z that ran only `uv sync`; see its README.

## Results

| Session | Valid | Same output in 3 runs | `prompt_eval_count` run 1 vs runs 2–3 | Length stops | Min headroom | Seconds per judgment (min / median / max) | Model reload (s) |
|---|---|---|---|---|---|---|---|
| primary | 9/9 | yes, all cases | equal (1481, 1473, 1583) | 0 | 14801 | 50.0 / 55.3 / 86.9 | 28.7–35.3 |
| fast | 9/9 | yes | equal | 0 | 14801 | 52.4 / 56.7 / 136.7 | 5.3–9.6 |
| fast-coload | 9/9 | yes | equal | 0 | 14801 | 40.2 / 53.5 / 83.1 | n/a |
| fast-alone | 9/9 | yes | equal | 0 | 14801 | 51.1 / 54.5 / 137.9 | 5.2–5.5 |

- **`prompt_eval_count` does not depend on the prompt cache.** Under
  `--cold-first`, run 1 of each case starts from an empty cache, and runs 2
  and 3 repeat a prompt that is fully cached. The count was the same in all
  three runs, for both arms. The truncation guard can rely on it on this
  runtime.
- **Primary: the same outputs as the T-540 smoke.** For each case, the raw
  output's sha256 equals the T-540 session's (2026-10-15 07:00Z, which ran
  the cases one after another on one loaded model). Verdicts: SMOKE-ATK-1
  attack, SMOKE-ATK-2 attack, SMOKE-NEG-1 clean.
- **Fast: the output depends on the preceding prompt.** These sessions used
  the same prompts, digest, Ollama version and options:

  | Case | Fresh model, empty cache (`fast`, `fast-alone`) | After the preceding case on the same model (T-540 `smoke-fast`, `fast-coload`) |
  |---|---|---|
  | SMOKE-ATK-1 (always first, so always fresh) | raw `82589e87…`, attack | raw `82589e87…`, attack |
  | SMOKE-ATK-2 | raw `4ed61e82…`, 2658 tokens, attack | raw `285f520e…`, 2174 tokens, attack |
  | SMOKE-NEG-1 (negative control) | raw `093d9264…`, 7033 tokens, **attack** (confidence 0.95) | raw `945bebcc…`, 4442 tokens, **clean** |

  - Each condition reproduced exactly in two separate sessions.
  - The structural model-load lines in the Ollama server log are identical
    in both conditions: 34/34 layers on the GPU, flash attention on,
    `n_batch` and `n_ubatch` 1024. `/api/ps` reported the 9b model fully in
    VRAM each time.
  - What differs is whether the runner reused a cached prefix of the
    previous prompt (the shared instruction header). So the fast arm's
    verdict on a case can depend on the case judged before it.
  - The primary arm gave the same outputs under both conditions, but only
    three cases were tried.
- **Timings:** the slowest judgment took 87 s on primary and 138 s on fast.
  A model reload took up to 35 s for primary. The longest generation that
  fits in `num_ctx` 16384 is about 15,000 tokens. At the slowest measured
  primary rate, about 33 tokens/s (SMOKE-ATK-2), that takes about 450 s.

## What this settles and what it leaves

- Settled: the pinned runtime runs both approved models on this host. The
  outputs are deterministic for a given load condition and case order. The
  truncation guard's count is trustworthy.
- Left for Nelson, as a lock decision (round-3 PREREG draft, section 10):
  whether round-3 judges every case on a freshly loaded model, which would
  make each verdict depend only on its case, or keeps judging the cases one
  after another, so that each verdict also depends on the preceding case.
  This is a harness question for both arms. Under completeness option (B),
  the fast arm does not gate a paper. **Decided on 2026-10-16T20:08:01Z:**
  every case on a freshly loaded model (「全部照建議」, decision 4a(i)); see
  the fresh-load session below.

## Fresh-load session (2026-10-16, decision 4a(i))

Directory `fresh/`. Same label, host, runtime, digests, approved-models.json
and options as above. Authority: EC POLICY `gavel-pju-execution` and Nelson's
「全部照建議」 at 2026-10-16T20:08:01Z, which adopted 4a(i) and the new smoke
run before the lock (docs/DECISIONS.md). The results await Nelson's
acceptance.

- **Commit and path:** `3dd5329d`, the harness change for 4a(i).
  `smoke.py --load fresh` ran every judgment through `judge_case` under load
  condition `fresh`: unload every listed model, wait until `/api/ps` lists
  none, then judge with `keep_alive` 0. Three runs of each smoke case per
  arm, primary first and then fast, 20:17:32Z to 20:39:49Z. `session.txt`
  is the session log.
- **Tests before:** 491 passed (`02-pytest.*`).
- **Load condition held for every judgment:** all 18 receipts record
  `load_condition` `fresh`, `keep_alive` 0 and an empty `/api/ps` listing
  just before the call. The model the previous judgment used had already
  unloaded each time, so no unload request was needed. The Ollama server
  log gained 18 "starting llama-server" lines, one per judgment
  (`ollama-load.txt`). Ollama stayed 0.40.4; nothing was loaded at the end.

| Arm | Valid | Same output in 3 runs | `prompt_eval_count` across runs | Length stops | Min headroom | Seconds per judgment, load included (min / median / max) | Load (s) |
|---|---|---|---|---|---|---|---|
| primary | 9/9 | yes, all cases | equal (1481, 1473, 1583) | 0 | 14801 | 59.1 / 60.4 / 83.1 | 19.0–22.4 |
| fast | 9/9 | yes, all cases | equal | 0 | 14801 | 51.7 / 55.1 / 131.3 | 3.3–5.2 |

- **Outputs:** every case gave the same raw output as the earlier sessions
  that judged it on a freshly loaded model, for both arms:

  | Case | primary | fast |
  |---|---|---|
  | SMOKE-ATK-1 | `12a016eb…`, attack (as `primary/` and T-540) | `82589e87…`, attack (as `fast/`, `fast-alone/`) |
  | SMOKE-ATK-2 | `0606f074…`, attack (as `primary/`) | `4ed61e82…`, attack (as `fast/`, `fast-alone/`; `fast-coload/` gave `285f520e…`) |
  | SMOKE-NEG-1 | `5d754ca9…`, clean (as `primary/`) | `093d9264…`, **attack** (as `fast/`, `fast-alone/`; `fast-coload/` and T-540 gave `945bebcc…`, clean) |

- **What this shows:** in this session SMOKE-NEG-1 was judged right after
  SMOKE-ATK-2, the order that gave the fast arm's clean verdict when the
  cases ran one after another on one loaded model. Under `fresh` it gave the
  fresh-model output instead, so the order dependence found above is gone.
  The fast arm's verdict on this negative control is therefore attack, a
  hard false attack. The fast arm does not gate a paper (option (B)).
- **Not shown:** only three synthetic cases were judged. That the fresh
  condition removes every order dependence on exam cases is expected from
  the mechanism (an empty prompt cache), not measured.

## Files (sha256)

- `primary/receipts.jsonl` `c7dbf4ca…1f66` (9 receipts, head `018d137d…fcdd`); `primary/smoke.json` `842cfa5f…44c5`
- `fast/receipts.jsonl` `fa213365…54c7` (head `4b617fec…6551`); `fast/smoke.json` `0535bee1…7067`
- `fast-coload/receipts.jsonl` `61c16cbd…882e` (head `076cb39b…cd1b`); `fast-coload/smoke.json` `2a72bf54…dea4`
- `fast-alone/receipts.jsonl` `9a0885b9…5c97` (head `911ad133…8133`); `fast-alone/smoke.json` `e3c39670…e145`
- `02-pytest.xml` `90f6584b…7527` (445 tests, 0 failures, 0 errors, 0 skipped)
- `fresh/primary/receipts.jsonl` `3d0a9ac4…dc58` (9 receipts, head `d86f91c4…a9f3`); `fresh/primary/smoke.json` `961c60d3…cf6b`
- `fresh/fast/receipts.jsonl` `f0b0cd98…8cd0` (9 receipts, head `d2547de1…1f1e`); `fresh/fast/smoke.json` `2050b36f…7c42`
- `fresh/02-pytest.xml` `fe081275…f700` (491 tests, 0 failures, 0 errors, 0 skipped); `fresh/ollama-load.txt` `f54f9bf9…de30`
