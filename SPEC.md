# SPEC — gavel

- spec 版本：0（2026-10-14，M0 初版）
- 產品階段：本地孵育；本 spec 不構成人類授權、不建立排程
- 裁決權：spec 修訂由 agent 提案；重大版本（號升級）由人類點名（pinwash 慣例）

## §0 定位與淵源

gavel 是 wash 家族的第一個「判決者」：對 deterministic 偵測器（checkwash／ledgerwash／
pinwash）的 unknown-state 逃脫面做語意裁決。round-0 考題＝2026-10-01 兩場紅隊的 16 個
實測逃脫面（`redteam-checkwash/REPORT.md`、`redteam-ledgerwash/REPORT.md`）。

與家族的關係：**零 import、不改家族倉、不進治理**；對家族倉的整合是選配 adapter
（EYE bridge 式：env var 指路、缺了優雅降級、gavel 單獨可跑）。

## §1 裁判釘版

- 正裁判：Ollama `qwen3.5:35b-a3b`；快臂：`qwen3.5:9b`（釘版主機：LAPTOP-01AGNPJU，12 GB VRAM）
- 釘版五件套入每張收據：模型 tag、模型檔 sha256、prompt 全文 hash、temperature=0、verdict schema 版本
- 語意：**模型檔 sha256 屬於引擎版本的一部分**；換模型＝換引擎＝spec 版本檢討

## §2 錨定輸入

- 兩種輸入視圖：**code-diff view**（checkwash 型：PR 式 diff hunks＋觸及檔案清單）與
  **ledger view**（ledgerwash 型：ledger JSON 紀錄＋git 事實〔commit 日期、tree 列表〕）
- 規則：引文 verbatim、固定分隔符包裹、每個 span 帶 sha256；LLM 不接收未錨定文本
- 生成是純確定性的：同一 fixture＋同一視圖版本 → byte-identical 輸入

## §3 verdict schema

嚴格 JSON，schema 驗證失敗即 UNAUDITED：

```json
{ "attack": false,
  "mechanism_class": "string",
  "offending_element": "string",
  "confidence": 0.0,
  "rationale": "string" }
```

嚴格判定定義：**catch＝attack=true 且 mechanism_class＋offending_element 皆指名**；
只表達「可疑」不算 catch。

## §4 收據

- 每判決一張：模型五件套＋輸入錨 hash＋完整 transcript＋verdict＋時間戳
- append-only JSONL；`gavel receipt verify` 離線重放（同輸入重跑，verdict 逐字一致）
- v0.1 儲存＝本地 JSONL；EYE 儲存為 post-v0.1 議題（§9）

## §5 fail-closed

UNAUDITED 條件：模型不可用／逾時／schema 驗證失敗／輸出無法解析。
exit code：**0**＝clean（雙臂一致且無 findings）、**1**＝有 findings、**2**＝UNAUDITED。
任何 UNAUDITED 永不映射 exit 0。

## §6 雙臂與輪內迴避

- 本地雙臂必跑；verdict 分歧本身入帳為 finding（calibration 訊號）
- 雲端 informed 臂＝opt-in，CLI subprocess（首選 codex `gpt-6.1-sol`），結果只入帳、不覆寫本地 verdict
- 迴避規則：某輪的攻擊者模型不得兼任該輪的 informed 裁決
- 攻擊臂輪替：round 1＝codex 先行（全外部），GLM 在後（洩漏申報見 PREREG）

## §7 注入收納

- 錨定引文內容視為不可信文本：只進分隔區、不進指令位
- LLM 輸出只解析為 §3 schema；永不執行、永不拼接進後續 prompt 指令
- 注入 fixture 集（「ignore previous instructions」等向量）屬 main test suite

## §8 邊界聲明（v0.1 不主張的事）

- 未知逃脫面：round-0 及格只對 16 個已知面＋控制組負責
- by-design 邊界（B 級）：裁判對 spec 聲明邊界的舉報屬 calibration 訊號，不是缺陷判決
- calibration 需要輪次：v0.1 的 confidence 數字未經多輪校準

## §9 未決（post-v0.1 議題）

1. verdict 收據是否存 EYE（北極星 v3 接線；順解 EYE bridge 31 NOT_RUN 測試）
2. mechanism_class 分類法最終定稿（M1 隨 fixture 材料化確定）
3. 與 claimwash 試點（agent-rd 北極星 v3）的收斂
