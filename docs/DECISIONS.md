# 決策記錄

## 2026-10-14（M0，人類裁決）

1. **命名：gavel**（候選 gavel／verdictwash／assize，人類點選 gavel）
2. **License：Apache-2.0**（正本取自 apache.org）
3. **本地孵育**：不開 GitHub、無遠端；qualify 過關＋round 1 存活後再談畢業（ledgerwash S0–S5 模式）
4. **round-0 及格線全案接受**：S 5/5 零容錯、A ≥4/5、B 不計分、否定控制硬 0／soft ≤2、
   agree ≥80%、S 級 3× 逐字一致
5. **家族決策閘細分**：
   - checkwash 三個 NEW 逃脫面（A05/A06/A16）開 issue 一事——**checkwash 施工中，
     gavel M0–M4 完成後再議**；gavel 期間不碰 checkwash repo
   - ledgerwash spec 4 候選（R1–R6、R9）——**人類授權收斂**，時程獨立於 gavel 進行

## 淵源決策（同日較早，依序）

- 方向：LLM-in-loop 裁決層（有別於家族無網路無 LLM 舊路線）；「先討論不動刀」
- 資源：雲端模型由人類提供；本地模型 agent 可依專案重建（可刪既有——實際未刪任何模型）
- 模型陣容：ZCode/GLM＋codex gpt-6.1-sol＋本地 qwen3.5 雙臂（35b-a3b／9b）；
  其餘雲端 CLI 退出本專案陣容
- codex 已復活（codex-cli 0.162.1）；ChatGPT 帳號模型正名＝`gpt-6.1-sol`（裸名 gpt-6.1 被拒）

## 2026-10-14 (backfilled 2026-10-15)

Nelson's gavel-related messages in the operator's ZCode session (`sess_d7c2b5b9-1b50-48cf-b3e5-3ce5697342f5`, LAPTOP-01AGNPJU), quoted verbatim with their UTC times, each followed by an English gloss. Multi-line messages are in text blocks so their line breaks are kept. The last two messages fall on 2026-10-15 UTC in the same session.

**2026-10-14T01:50:08Z**: Read checkwash in full, read-only; asks whether the agent is confident it could build a new repository of similar maturity.

```text
用唯獨完整看過checkwash
你覺得你有信心打造一個成熟度差不多的全新repo嗎
```

**2026-10-14T01:53:38Z**: Wants to build something different this time; earlier projects took a strict no-network, no-LLM route; asks which direction to take next.

```text
敖交給我 這次我想打造一個比較不一樣的 
之前都是以嚴格 無網路 無llm的路線 你覺得接下來目標建議走什麼
```

**2026-10-14T02:00:10Z**: LLMs may be connected; discussion only, no implementation yet. Asks (1) whether the existing repositories are to be used as resources and (3) whether EYE's LLM is suitable; suggests (2) that, for an LLM route, the agent first scan this computer's configuration and installed local models.

```text
可以接上llm  
這邊先討論 不動刀
1.所以是把現有repo當成資源?
2.如果走llm的話 我覺得你可以先掃一下我電腦配置和已有本地模型 
3.eye的llm你覺得適合?
```

**2026-10-14T02:04:40Z**: Check the CLIs too: (1) Nelson can provide cloud models; (2) the agent may set up the local models this project recommends, and may delete Nelson's local models to do so.

```text
cli你也先確認一次 
1.我可以提供雲端模型
2.你也可以依照這個專案建議的本地模型自行建置(可以刪掉我的本地模型 建置你要的)
```

**2026-10-14T02:13:41Z** 「你幫我先試跑一次codex cli , 模醒選6.1 high」: Do a first trial run of the codex CLI, model 6.1, high.

**2026-10-14T02:16:46Z** 「這邊改一下 你自己+codex +本地雙臂」: Change this: the agent itself + codex + the local dual arms.

**2026-10-14T02:20:24Z** 「可以 先把草案列出」: OK; list the draft first.

**2026-10-14T02:24:59Z**: Is this version enough for 0.1? Plan a complete version.

```text
我覺得這版夠進0.1了?
規劃一版完整的看看
```

**2026-10-14T02:30:19Z**: Answers to five decision points: (1) gavel; (2) Apache-2.0; (3) local incubation; (4) accepted; (5) split this one: checkwash is under construction, look again after the first four are done; ledgerwash may converge. Recorded as the M0 entries above.

```text
1.gavel
2.Apache-2.0
3.本地孵育
4.接受
5.這邊要細分 checkwash施工中 等你做完前面4個在看 可收斂legerwash
```

**2026-10-14T02:36:15Z** 「動刀」: Start implementing.

**2026-10-14T03:07:22Z** 「可以」: OK. The round-0 receipts start at 03:10:04Z.

**2026-10-14T11:04:59Z** 「重考 pass前不發」: Retake the exam; do not release before a PASS. Recorded in PREREG Addendum 3; the round-1 receipts start at 11:09:25Z.

**2026-10-14T11:23:38Z** 「你目前的專案路徑在哪」: Where is your current project path?

**2026-10-14T13:05:12Z** 「開M4」: Start M4 (the external attack round). The attack round-1 receipts start at 13:25:39Z.

**2026-10-14T14:05:48Z** 「這版推上去 走EC派工流程」: Push this version, through the EC dispatch process. The repository was then published on GitHub, so M0 item 3 above (「不開 GitHub、無遠端」) no longer describes it.

**2026-10-14T14:33:05Z** 「好了」: Done.

**2026-10-14T14:38:42Z** 「確認一下：要修改的是 agent-checkwash（ID 21103431）嗎？我會只新增 gavel，沿用它現有權限：程式碼、Issues、PR、Workflows 可讀寫，Actions／Metadata 唯讀；其餘 10 個倉庫與權限不變」: Asks to confirm that the GitHub App installation to change is agent-checkwash (ID 21103431); only gavel is to be added, with the installation's existing permissions (code, issues, PRs and workflows read/write; Actions and metadata read-only), and the other 10 repositories and the permissions stay unchanged.

**2026-10-14T14:43:09Z** 「好了」: Done.

**2026-10-14T14:49:04Z** 「在試一次」: Try again.

**2026-10-14T14:53:06Z** 「好了」: Done.

**2026-10-14T14:57:29Z** 「找antigravity cli , 找到gemini4 argon , 列入重考」: Find the Antigravity CLI, find Gemini 4 Argon, and include it in the retake. The gemini-4-argon-high entry of `approved-models.json` quotes this message.

**2026-10-14T15:06:46Z**: A review with P0/P1 items: check completeness before scoring; make receipt verification and model pinning real (approved-model manifest, content checks, replay as a separate feature); add a separate inconclusive result; split the next round into a regression paper and an unseen sealed paper with paired cases; keep dual-arm divergence and generate reconciliation tables, correcting the ATK-005 prediction claim; then a small real-review pilot.

```text
我這邊有幾個想法 你看看
P0：先補資格考的完整性檢查。
qualify.evaluate() 有幾個值得先修的缺口：否定控制缺結果或 UNAUDITED，可能不被算成失敗；重現性檢查沒有強制每題一定完成三次；A 級門檻會隨傳入題數縮小。這讓「考試沒做完整」存在取得 PASS 的路徑，屬於靜態程式可見的問題。評分程式
**具體做法：**鎖定考卷清單、各組題數、雙臂與必要重跑次數；先確認全部收據齊全且有效，再計算成績。缺件就不發資格。

P0：把「收據驗證」與「釘版」真正做實。
現在收據驗證主要檢查欄位與識別碼，沒有把判決、原始回覆、prompt 等內容全部納入一致性驗證；模型也只是記錄當下 tag 的 digest，尚未強制比對核准版本。收據實作、模型實作
**具體做法：**保存完整輸入、prompt、原始回覆與執行設定；驗證時重算內容 hash，重新解析回覆並比對判決。另設核准的模型 manifest，不符就 UNAUDITED。把「內容完整性驗證」與「重新執行模型」拆成兩個明確功能。
這是 Gavel 的核心可信度，值得排在增加模型前面。

P1：把「證據不足」獨立成一種結果。
現在 prompt 把「無法從證據證實攻擊」導向 attack=false，但缺乏上下文與確認沒有弱化，是不同情況。目前 prompt
我建議增加 INCONCLUSIVE／需要補證據，並要求每筆 finding 說清楚：
「原本哪項保護 → 如何改變 → 引用哪段證據 → 還缺什麼」。
對 E1 的修復，也應要求指出實際存在的替代綁定機制。遷移文件可以解釋變更，但不能單憑作者宣稱就證明保護仍然存在。原本核准的規格與本次修改內容，也要分開呈現。

P1：下一輪必須分開「回歸卷」與「未曝光考卷」。
round-1 是針對已知漏題修改 prompt，再用相同 24 題重考。它能支持修復有效，但對未知案例的能力仍需另外驗證。round-1 報告
**具體做法：**舊題與 ATK 案例全部進回歸卷；另由沒參與 prompt 修補的人準備密封卷，鎖定版本後才揭曉。尤其補成對案例：同樣是刪除舊欄位，一案真的失去保護，另一案有可查驗的等價替代。這才能測出它理解的是保護能力，而不只是看到刪除就報警。

保留雙臂分歧的價值，並把報告對帳自動化。
E1 是 35b 漏判、9b 抓到，所以應分別報告「單臂漏判」和「整體是否放行」。這也支持保留分歧送審，不能只依模型大小或自報信心選答案。外部攻擊報告
另外有一處需要直接更正：報告寫 Codex 預測到 ATK-005 的 primary 逃脫，但原始 PREREG 預測雙臂都是 attack=true。預測、實測、命中率應由固定資料產生表格，避免摘要改寫了原始紀錄。原始預測

產品上，先完成一個小範圍的真實覆核試點。
我會先選一個家族工具、連續收集一小批真實變更，讓 Gavel 提供意見，由人確認。第一輪只回答四個問題：多抓到了什麼、誤報了什麼、多少案需要補證據、每案增加或節省多少人工時間。
```

**Codex-authored text relayed by Nelson.** Apart from its first line, 「我這邊有幾個想法 你看看」, this message is text from a review that Codex wrote in a separate Codex Desktop session on LAPTOP-01AGNPJU (session `01a13aed-c745-7f23-aa90-318ab7e4a98c`), pasted here by Nelson. In that session Nelson asked 「用你的角度 給gavel 具體建議」 (2026-10-14T15:00:42Z), and Codex completed the review at 15:04:05Z. The paste is an edited excerpt: it leaves out the review's two opening paragraphs, its link targets, the last paragraph of its sixth item (beginning 「我最想看到的下一個成果」) and its last sentence, 「以上是靜態審閱，本輪沒有改倉或執行測試。後續重考與模型負載應依你的工作機規則，安排到核可的 pool。」 (The above is a static review; this round did not change the repository or run tests. Later retakes and model load should follow your work-machine rule and be scheduled on an approved pool.)

**2026-10-14T15:11:49Z** 「開始」: Start. The round-2 receipts start at 15:56:22Z.

**2026-10-15T00:08:28Z** 「繼續」: Continue. The four recorded round-2 re-attempt receipts follow (00:11:06Z to 00:19:26Z).

**2026-10-15T00:26:56Z** 「目前工作區?」: Current workspace?

Notes:

- `approved-models.json` records `approved_at` `2026-10-14T15:00:00Z` and an `approved_by` beginning "human in conversation" for all three entries. No message above has that time; the nearest are 14:57:29Z and 15:06:46Z. No message above explicitly approves the qwen manifest digests (`3460ffee…`, `6488c96f…`) or PREREG Addenda 4 and 5. The gemini-4-argon-high entry does follow the 14:57:29Z message, which it quotes.
- `cases/round-2-sealed/SEALED-PREREG.md` says its authoring session was "assigned by the human". That codex session was started by the operator agent (`codex exec`, about 2026-10-14T15:26Z) after 「開始」 at 15:11:49Z; no message above assigns it. The proposal that someone outside the prompt fixes prepare a sealed paper is in the relayed 15:06:46Z text.

## 2026-10-15

Nelson's messages in the takeover session (Claude Code on LAPTOP-01AGNPJU), quoted verbatim with their UTC times:

**2026-10-15T00:28:29Z** 「接手 gavel」: Take over gavel. (Followed by a pasted list of the previous operator's gavel paths, not reproduced here.)

**2026-10-15T01:54:17Z** 「你先規劃給我」: Plan it for me first.

**2026-10-15T03:18:03Z** 「照你建議做」: Do as you recommend. This adopted all five recommendations of the takeover plan of 2026-10-15:

1. **D1(a) Round-2 disposition.** Round-2 is closed as INCOMPLETE under the locked contract. The status of record is the first pass; the re-attempts are disclosed and not counted. Primary-arm verdicts are unscored observations. SP-001..SP-012 are no longer sealed and become known regression cases for round-3. All results produced on the work machine (round-0, round-1, M4 wave-1, round-2, test runs) stay 未驗收. v0.1.0 stays frozen until a round-3 run on the EC pool passes. Details: the ERRATUM in `results/round-2/REPORT.md`.
2. **D2(A) Where gavel runs.** Execution only through EC pool workloads: a model-free gavel-verify first, and the judge only on a pool host Nelson names. Model work is BLOCKED until then.
3. **D3(a) EC tasks.** EC rows T-537, T-538 and T-539 were retired as CANCELLED on 2026-10-15 (EC commits ed2064ee0, 784e29103 and b3b5f73f5; evidence `evidence/requests/29499990-6719-4a7a-8b2e-0599b98b5246/gavel-disposition-20261015.md` in the private EC repository). gavel follow-up lives in taipei49314/gavel.
4. **D4(a) Agent rules.** The work-machine rule was added to the ZCode client's user rule file and refreshed in the other agent CLIs' rule files.
5. **D5(a) Publication.** Changes are published in batches. Each push and PR needs Nelson's named OK; merges stay with Nelson, or with an agent for a PR he names; tags and releases are authorized separately. Batch 1, this status correction, was approved with this decision.
