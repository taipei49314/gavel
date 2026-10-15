# gavel

釘版本地 LLM 裁判——wash 家族 deterministic 偵測器的語意裁決層。

gavel 對家族工具（checkwash／ledgerwash／pinwash）的殘餘風險面做判決：那些 deterministic
規則看不見、紅隊實測會逃脫的形狀（unknown-state escapes），由一顆被釘死的本地模型在嚴格的
籠子裡裁決。

## 它承諾什麼（v0.1.0 語意）

- ~~裁判通過 round-0 資格考：16 個已知逃脫面（S 級 5/5 零容錯、A 級 ≥4/5）＋否定控制組零誤傷~~ **[Correction 2026-10-15]** Round-0 recorded FAIL ([results/round-0/REPORT.md](results/round-0/REPORT.md)), and no judge is qualified; see Status below.
- 每個判決是一張收據：模型 sha256、prompt hash、完整 transcript、verdict——~~離線可重放~~ **[Correction 2026-10-15]** Replay is not implemented: at d0cb1dc, `gavel verify` has only `--content`, which re-hashes stored content and re-parses stored responses without running a model. The 「完整 transcript」 claim does not hold for UNAUDITED receipts: they keep no raw response (`raw_response` is null), for example `results/round-2/regression/receipts.jsonl` line 43 and `results/round-2/sealed/receipts.jsonl` lines 38–39.
- fail-closed：模型不可用／schema 違規 → UNAUDITED（exit 2），永不 exit 0

## 它不承諾什麼

- 不保證未知逃脫面——那是 round 1+ 的事
- 不是修復工具——只有判決
- 不推翻 spec 聲明的 by-design 邊界（B 級案例僅入帳 calibration）

## 籠子（設計不變項）

1. **錨定輸入**：LLM 只見 sha 錨定的 verbatim 引文，永不接觸未錨定自由文本
2. **釘版裁判**：GGUF sha256＝引擎版本的一部分、temp 0、~~verdict 可重放~~ **[Correction 2026-10-15]** Replay is not implemented; see the receipt correction above. Receipts of the local arms record the Ollama manifest digest (`pin.manifest_digest`, for example `3460ffee…` for qwen3.5:35b-a3b), not the GGUF file's sha256; the manifest names the GGUF layer by its sha256 digest.
3. **雙臂憲法**：本地雙臂（35b 正裁判＋9b 快臂）必跑；雲端 informed 臂 opt-in；攻擊者禁任同輪裁判 **[Correction 2026-10-15]** At d0cb1dc only `gavel scan` leaves the informed arm out by default; `gavel pin` and `gavel qualify` include it by default (`gavel/cli.py` lines 119 and 145). `gavel scan --arms informed` sends the cloud model id to Ollama, because `cmd_scan` calls `judge_case` without the agy transport (`gavel/cli.py` line 57).
4. **runtime 零第三方依賴**：Ollama 走 localhost REST（urllib）、雲端走 CLI subprocess
5. **注入收納**：固定 verdict schema、輸出永不執行

## 狀態

**Status (2026-10-15)**

- **No judge is qualified.** Round-0 recorded FAIL. Round-1 and round-2 were run on work machine LAPTOP-01AGNPJU, and neither is a qualification of record.
- **Round-2 is closed as INCOMPLETE** under its locked contract (PREREG Addendum 4 completeness gate). The first pass is the status of record; later re-attempts are disclosed and not counted. See the ERRATUM in [results/round-2/REPORT.md](results/round-2/REPORT.md).
- **All exam results are 「未驗收」** (not accepted) under EC POLICY work-machine-local: round-0, round-1, attack round-1 and round-2. So are the test runs made on the work machine.
- **Next steps**, all on the EC pool: a model-free `gavel-verify` workload; then the judge on an EC pool host that Nelson names (model work is BLOCKED until then); then round-3.
- **v0.1.0 stays frozen** until a round-3 run on the EC pool passes.
- Decisions of record: [docs/DECISIONS.md](docs/DECISIONS.md). Where the paragraph below differs from this block, this block is current.

已上架（github.com/taipei49314/gavel，main）。spec 0；~~裁判已通過 round-1 資格考（results/round-1/REPORT.md）~~；**[Correction 2026-10-15]** Round-1 was run on work machine LAPTOP-01AGNPJU and is 未驗收; it is not a qualification of record (see Status above).
M4 外部攻擊輪 wave-1 已入帳（attack/round-1/REPORT.md，1 個新逃脫面 E1 已披露為 known-limitation）。
v0.1.0 tag 尚未發行：候選條件＝~~round-2 重考（prompt v4＋考卷 v2）PASS~~。**[Correction 2026-10-15]** Round-2 is closed as INCOMPLETE; v0.1.0 stays frozen until a round-3 run on the EC pool passes (see Status above).
License：Apache-2.0。人類決策記錄見 [docs/DECISIONS.md](docs/DECISIONS.md)。
設計細節見 [SPEC.md](SPEC.md)；round-0 考題與及格線見 [PREREG.md](PREREG.md)。
