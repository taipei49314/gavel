# gavel

釘版本地 LLM 裁判——wash 家族 deterministic 偵測器的語意裁決層。

gavel 對家族工具（checkwash／ledgerwash／pinwash）的殘餘風險面做判決：那些 deterministic
規則看不見、紅隊實測會逃脫的形狀（unknown-state escapes），由一顆被釘死的本地模型在嚴格的
籠子裡裁決。

## 它承諾什麼（v0.1.0 語意）

- 裁判通過 round-0 資格考：16 個已知逃脫面（S 級 5/5 零容錯、A 級 ≥4/5）＋否定控制組零誤傷
- 每個判決是一張收據：模型 sha256、prompt hash、完整 transcript、verdict——離線可重放
- fail-closed：模型不可用／schema 違規 → UNAUDITED（exit 2），永不 exit 0

## 它不承諾什麼

- 不保證未知逃脫面——那是 round 1+ 的事
- 不是修復工具——只有判決
- 不推翻 spec 聲明的 by-design 邊界（B 級案例僅入帳 calibration）

## 籠子（設計不變項）

1. **錨定輸入**：LLM 只見 sha 錨定的 verbatim 引文，永不接觸未錨定自由文本
2. **釘版裁判**：GGUF sha256＝引擎版本的一部分、temp 0、verdict 可重放
3. **雙臂憲法**：本地雙臂（35b 正裁判＋9b 快臂）必跑；雲端 informed 臂 opt-in；攻擊者禁任同輪裁判
4. **runtime 零第三方依賴**：Ollama 走 localhost REST（urllib）、雲端走 CLI subprocess
5. **注入收納**：固定 verdict schema、輸出永不執行

## 狀態

本地孵育中（未公開、無遠端）。spec 0；v0.1.0 進行中。
License：Apache-2.0。人類決策記錄見 [docs/DECISIONS.md](docs/DECISIONS.md)。
設計細節見 [SPEC.md](SPEC.md)；round-0 考題與及格線見 [PREREG.md](PREREG.md)。
