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

## 2026-10-15 (afternoon and evening)

Nelson's later messages in the same takeover session, quoted verbatim with their UTC times.

**2026-10-15T06:45:26Z**, one message answering five open items:

```
1.可以代合
2.我zcode那邊不會再用了 當作不存在就好
3.推
4.用pju 我知道不行 但這次授權
5.不啟用
```

1. The agent may merge PR #1. It was merged as `9d5d96d`.
2. The ZCode client will not be used again; treat it as nonexistent.
3. Publish batch 2. This is PR #2.
4. Run on LAPTOP-01AGNPJU. The message acknowledges the work-machine rule and gives a one-time authorization. For that one session only, it replaces the pool-host route of D2(A).
5. Do not enable the ZCode guard hook.

**2026-10-15T06:55:07Z** Scope of item 4. Asked how far "this time" reaches, Nelson chose 「驗證 batch 2＋裁判冒煙 (Recommended)」:
- a locked virtual environment;
- the full test suite at PR #2's exact head;
- `gavel verify --content` on the committed receipts;
- round-2 table regeneration;
- a judge smoke on the three smoke cases only.

Excluded: exam papers, round-3, the informed arm, agy and codex.

How it was recorded and run:
- It was recorded in the private EC repository before any run, as the one-time POLICY row `gavel-pju-verify-once-20261015` (task T-540, EC commit `2d8f51534`).
- The session ran from 06:58:44Z to 07:10:29Z at `4927436d`:
  - 445 tests, with 0 failures, 0 errors and 0 skips;
  - `verify --content` OK on all six committed receipts files (287 receipts);
  - round-2 regeneration byte-identical at two hash seeds; as locked, both papers are INCOMPLETE, which matches D1(a); as reported, the committed `report.json` files are reproduced;
  - judge smoke on Ollama 0.40.4 with both manifest digests verified: 12/12 judgments valid, the three primary runs identical for every case, no truncation.
- The results are labelled "human-authorized local PJU, NOT EC pool". The grant was consumed (`05b32cf66`) and T-540 closed (`170a8976b`). Raw evidence is in the EC task.

**2026-10-15T09:41:31Z** 「可以合 結果接受 round3 我會在另一台電腦準備」: Merge PR #2. The results are accepted. Nelson will prepare round-3 on another computer.

Notes:
- The acceptance covers the T-540 session results above, nothing else. Under D1(a), the round-0, round-1, M4 wave-1 and round-2 exam results stay 未驗收, and no judge is qualified. v0.1.0 stays frozen.
- Round-3 still needs Nelson to:
  - approve its design and lock (`docs/proposals/round-3-PREREG-DRAFT.md`);
  - name its venue, with a new authorization if that is a work machine;
  - commission a new sealed paper from a model family gavel has never used.

## 2026-10-15 (standing authorization for LAPTOP-01AGNPJU)

Nelson's later messages in the same takeover session, quoted verbatim with their UTC times.

Times are when each message reached the session; the 09:47:21Z message was queued at 09:46:50Z and the 09:49:47Z message at 09:49:42Z, each delivered when Nelson interrupted a pending step; the repeat send is dated by its queue time.

**2026-10-15T09:47:21Z** 「等等我確認一下 你現在工作的機台是哪一台?」: Wait, let me check: which machine are you working on now? The assistant answered that it was on LAPTOP-01AGNPJU.

**2026-10-15T09:48:06Z** 「那如果是pju可以繼續執行了 我要離開的是518」: Then, if it is PJU, it can carry on; the one I am leaving is 518. 「518」 is LAPTOP-16NUA5I8: the computer Nelson was leaving was LAPTOP-16NUA5I8, not LAPTOP-01AGNPJU.

**2026-10-15T09:48:43Z** 「round3 用pju」: Use PJU for round-3.

Before running anything, the assistant replied (09:49:13Z) that a round-3 exam is judge load on a work machine, which conflicts with EC POLICY work-machine-local, and that under that row it had to stop, point out the conflict and wait for an explicit answer. It added that round-3 could not start yet in any case: Nelson's approval of the PREREG lock, the model family of the new sealed paper's author and N, the number of cases in that paper, were still open.

**2026-10-15T09:49:47Z** 「這個專案授權使用pju跑 因為所有資源都在pju」: This project is authorized to run on PJU, because all of its resources are on PJU. Nelson sent the same text a second time (queued at 09:49:57Z) while the assistant was already working.

How it was recorded:
- In the private EC repository, as the standing POLICY row `gavel-pju-execution` (task T-542; POLICY commit `f1572fe3f`; T-542 closed in `23a753fce`; evidence `evidence/requests/294885df-7774-4238-accb-7adff594e036/gavel-pju-standing-authority.md`). The row's 規則 cell is the authoritative text; [AGENTS.md](../AGENTS.md) section 1 quotes it byte-for-byte.

What it covers, for gavel work only, on LAPTOP-01AGNPJU only, until Nelson revokes it:
- building gavel virtual environments from the committed `uv.lock`;
- running gavel's tests and verification;
- running the judge through the committed harness, with the Ollama already on that host and the models whose digests are approved in `approved-models.json`: smoke runs, qualification rounds including round-3, and later exams. Every judgment is receipted, and the receipt records the host.

What stays with Nelson:
- each exam's PREREG is locked, and Nelson approves the lock, before the exam;
- qualification verdicts, acceptance of results, merges, tags and releases.

Results are labelled "human-authorized local PJU, NOT EC pool".

What it does not cover:
- any other project's load;
- LAPTOP-16NUA5I8;
- host security, service, permission, runner, label or profile changes;
- installing, upgrading or reconfiguring Ollama, or adding or removing models, without Nelson's separate OK;
- agent CLIs (agy, codex or others) as judge arms without Nelson's separate OK;
- presenting any result as EC pool evidence;
- retroactive acceptance of earlier work-machine exam results.

Effect on earlier decisions:
- For gavel on LAPTOP-01AGNPJU, it supersedes the venue part of D2(A) (execution only through EC pool workloads, the judge only on a pool host Nelson names), and with it the proposal to remove the LAPTOP-01AGNPJU pin from SPEC §1 (`docs/proposals/spec-clarifications.md`); on any other host D2(A)'s EC pool route still applies.
- D1(a) is unchanged. Round-2 stays closed as INCOMPLETE, and the round-0, round-1, M4 wave-1 and round-2 exam results stay 未驗收. No judge is qualified. D1(a) keeps v0.1.0 frozen "until a round-3 run on the EC pool passes"; Nelson has not said whether a round-3 pass on LAPTOP-01AGNPJU meets that condition. That is his decision, as are the qualification verdict and the acceptance of results (EC POLICY `gavel-pju-execution`), and any release needs his separate authorization (D5(a)).
- The 09:41:31Z acceptance above still covers the T-540 session results only.
- This answers the round-3 venue item in the 09:41:31Z notes above (「round3 用pju」 at 09:48:43Z, with the standing authorization of 09:49:47Z). Approval of the round-3 design and lock, and the new sealed paper from a model family gavel has never used, are still open.

## 2026-10-15 (round-3 preparation)

Nelson's messages and answers in the session that took gavel over again with 「接手gavel」 at 2026-10-15T17:13:11Z (2026-10-16 01:13 +0800), quoted verbatim with their UTC times. The answers to the assistant's questions are quoted as the option labels he chose; where an option carried a description, it is quoted too, because the label alone does not say what was approved.

**2026-10-15T17:16:15Z** 「開始實驗 直接朝你規劃 你執行 遇到重大決策問我」: Start the experiment; go straight at your plan; you execute; ask me about major decisions. The assistant's preceding report had named the pre-lock smoke run (round-3 PREREG draft, section 2) as the next step inside EC POLICY `gavel-pju-execution`, and had said that pushing its results still needed his OK.

**2026-10-15T17:23:48Z** Answers to four questions:

1. Asked whether to freeze Ollama's automatic updates for round-3 (the host's Ollama app setting `auto_update_enabled` was 1, with an hourly check), Nelson chose 「授權我關 (Recommended)」, described as 「我只把 Ollama 設定裡的 auto_update_enabled 改成 0，改完讀回驗證；不升級、不重啟、不動模型。round-3 結束後再問你要不要開回來。」 This is the separate OK that EC POLICY `gavel-pju-execution` requires for an Ollama configuration change, for this one setting.
2. Asked which arms decide a round-3 paper's completeness (the question proposed `primary` as the gating arm), he chose 「(B) 只看 primary (Recommended)」: a paper's manifest lists only the gating arm `primary`; the fast arm runs as a separate observation manifest over the same cases, reported but not gating. As the round-3 draft discloses, option (B) was proposed after round-2's results were known (round-2's gaps were all fast-arm cells).
3. Asked how pushes during round-3 preparation and execution are authorized, he chose 「整個 round-3 授權 (Recommended)」, described as 「準備分支可以由我推送並開 PR；開考時每份卷的開始和結束紀錄也由我推送，推送時間就是時間錨點。合併、鎖定核可、資格裁定和結果接受仍歸你。」 This is the named OK of AGENTS.md rule 9 for round-3: the agent pushes round-3 preparation branches and opens their PRs, and pushes each paper's start and end run records; merges, the lock approval, the qualification verdict and the acceptance of results stay with Nelson.
4. Asked which model family should author the new sealed paper N (Qwen, GLM, GPT/codex, Gemini and Claude are already used), he answered 「目前資源就這樣了」: these are the resources there are for now.

**2026-10-15T17:26:27Z** Asked how to proceed with N, given that no other computer is available and that LAPTOP-01AGNPJU holds two unused families (the grok CLI, xAI; the MiMo desktop app, Xiaomi), whose use there would conflict with the draft's rule that the key is never on LAPTOP-01AGNPJU before reveal and is outside EC POLICY `gavel-pju-execution`, he chose 「等有資源再說」, described as 「先把 R、K 和鎖定包準備好，N 等以後有新的家族或別台電腦。」: prepare R, K and the lock packet now; N waits until a new family or another computer is available.

What was done on these answers:
- Ollama: at 2026-10-15T17:25:36Z the agent set `auto_update_enabled` from 1 to 0 in the settings row of `%LOCALAPPDATA%\Ollama\db.sqlite` and read 0 back on a new connection. The database files were copied first (sha256 `70331fb3…04ac9` db.sqlite, `6dd0685e…bebab7` -shm, `f6ad5894…bd929` -wal, kept outside the repository). Ollama stayed 0.40.4; nothing was installed, upgraded or restarted, and no model was added or removed. Not verified: whether the running Ollama app reads the setting again at each hourly check; it was not restarted. Every paper's preflight refuses a daemon whose version is not the pinned one, so an update would stop a paper before its first judgment, or make a judgment UNAUDITED if it happened during the call.
- Completeness (B) and the push authorization are written into the round-3 PREREG draft. N stays required by the draft for a round-3 pass; it is deferred, not dropped.

**2026-10-16T00:20:32Z** 「先收尾 換電腦」: Wrap up first; I am changing computers. It came in place of an answer to the question asked at 2026-10-15T18:13:11Z. That question asked whether round-3 judges every case on a freshly loaded model, or keeps judging the cases one after another on one loaded model (round-3 PREREG draft, section 10, item 4a). That decision stays open. The agent stopped experimenting, recorded the pre-lock smoke results, and pushed the preparation branch under the round-3 push authorization of 17:23:48Z, without merging it.
