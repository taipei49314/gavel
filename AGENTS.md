# AGENTS.md

Rules for any agent, of any model and in any client, that works on gavel. They follow Nelson's decisions of 2026-10-15 (D2(A), D4(a) and D5(a) in [docs/DECISIONS.md](docs/DECISIONS.md)). When in doubt, stop and ask Nelson.

## 1. EC POLICY rows

The two rule cells below are copied byte-for-byte from the 規則 column of `POLICY.md` in Nelson's private estate-consolidation (EC) repository at commit `1f83bdc7026620f66e6afb811d88130d9748e23c`. Quote them; do not paraphrase them when passing them on. If EC POLICY changes, the current EC text governs.

### `workload` (scope 「兩台工作機與 pool」; type standing; status conditional; ruling T-195)

> 工作機 LAPTOP-01AGNPJU 與 LAPTOP-16NUA5I8 不跑引擎負載，包括測試、sweep、重判、校準與產品完整驗證（已授權發版的驗證也一樣），這些一律走 pool；工作機只做秒級的治理檢查。人類 2026-09-22「loading 不放這台 pju也不要放loading」（evidence/requests/a1f50d1f-6e08-4a59-9eb0-cdbd485803b0/no-load-on-either-work-machine.md）。

### `work-machine-local` (scope 「兩台工作機（LAPTOP-01AGNPJU、LAPTOP-16NUA5I8）上本機可做的事」; type standing; status active; ruling T-473)

> 兩台工作機本機只做下列事，都不執行產品程式；清單以外一律照 `workload` 走 pool，同時符合兩邊時以走 pool 為準。各項仍要有授權，本列不代替授權。(1) 讀檔，為定位或核對而搜尋（含 session 紀錄與日誌）。(2) 編輯文件與程式碼（不執行）。(3) git 版本控制操作（會跑測試或建置的 hook 除外）；gh 讀取、開 PR、看 CI 與日誌，依授權合併；gh workflow run 只用於已入 EC 帳的派工（PLAN §2）。(4) 讀 harness 已寫出的結果檔（JSON、JUnit、log）：可用 grep、jq、對單一檔 sha256sum，或 Python 標準庫唯讀解析；篩選與計數只依檔裡已寫的值，不 import 產品或測試程式碼，不從原始來源產生新數字。(5) 用 hostname 確認所在主機。(6) 執行 EC 的 Python 治理工具（ec_task、ec_status、ec_pr、ec_contracts 等），不含測試。(7) 派讀檔推理的唯讀 agent；派多個前先向人類預告規模與 token。不論多短都算負載：任何 pytest 呼叫（含 --collect-only）、產品 CLI（含 --version）、py_compile、建 venv 或安裝相依、建置、lint、型別檢查、sweep、重判、量測、probe、跨平台比對，以及用批次、矩陣或對局啟動 agent 或模型來產生結果。WSL、容器、VM、背景工作與從本機啟動的子 agent 都算本機。人類說「在本地做」「開跑」「執行」而沒指明主機時，先問在哪跑；人類明說在工作機跑時，停下並指出與本列的衝突，等明確答覆，不給一次性例外。沒跑的驗證記 `NOT_RUN：工作機規則（POLICY work-machine-local），<原因>`，不寫成通過。2026-09-22 之後在工作機產生的結果是「未驗收」，要當依據須在 pool 重做，或由人類明文接受。派子 agent 時把本列原文放進 prompt，不轉述。拿不準就問人類。

## 2. gavel rules

1. Run `hostname` first. LAPTOP-01AGNPJU and LAPTOP-16NUA5I8 are work machines; if you cannot tell where you are, assume a work machine.
2. On LAPTOP-01AGNPJU or LAPTOP-16NUA5I8, never run tests, the gavel CLI, Ollama, agy or codex. This includes any pytest call (even `--collect-only`) and any gavel CLI call (`python -m gavel` and `--version` included). WSL, containers, VMs, background jobs and sub-agents started from these machines count as the same machine.
3. Execution happens only through approved EC pool workloads. The model-free `gavel-verify` workload comes first; the judge runs only on an EC pool host that Nelson names. Until then, model work is BLOCKED.
4. Record a check that was not run as `NOT_RUN：工作機規則（POLICY work-machine-local），<原因>`, with the reason in place of `<原因>`. NOT_RUN is never written as a pass.
5. PREREG and REPORT files are append-only: `PREREG.md`, `attack/round-1/PREREG-codex.md`, `cases/round-2-sealed/SEALED-PREREG.md`, and every `REPORT.md` under `results/` and `attack/`. Corrections go in a dated section appended at the end.
6. No rule, threshold or prompt changes after results are known. A change needs a new round with a new PREREG, locked before that round runs.
7. A sealed answer key is never committed in plaintext before its reveal; only a salted sha256 commitment is committed. The key is never placed in any judge arm's working directory.
8. Every human approval is quoted verbatim, with its UTC time, in `docs/DECISIONS.md`.
9. Pushes need Nelson's named OK. Publication goes in batches, each pushed and opened as a PR only after his OK; merges stay with Nelson; tags and releases are authorized separately (D5(a)).
