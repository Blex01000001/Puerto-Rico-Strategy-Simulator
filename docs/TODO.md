# TODO — 目前狀態

記錄專案目前的待辦、已知問題與想法。標記：【直接做】使用者點名就能動手；【先討論】會改架構／輸出格式／引入新工具或方向未定；【使用者】需使用者自己操作。維護規則見 `CLAUDE.md`。

## 待辦

1. 【先討論】第二階段：手寫規則策略（`Engine/Strategies/RuleBased/`）— 先決定要比較哪些策略原型（例：玉米出貨流、菸草／咖啡流、建築優先）與參數化方式（`params` 欄位）。
2. 【先討論】MCTS 策略：模擬次數放設定 `params.simulations`；每次 rollout 用 `Clone()` ＋ `ReseedRng`；隱藏資訊不遮罩（約定不讀對手 VP）。
3. 【先討論】Dashboard（Blazor Interactive Server）：先定義要看的圖表（策略勝率、分數分佈、座位優勢、終局原因），結果檔格式見 `SimulationResult`。
4. 【直接做】RunPod 部署說明與發佈指令（`dotnet publish -c Release -r linux-x64`），寫進 CLAUDE.md；視需要加 `--summary-only` 之類的輸出選項。

## 已知問題／限制

- 規則中未明說、引擎採用的詮釋（請使用者確認，或提供反例）：
  - Factory 的金幣依「公式產量 > 0 的貨種數」計算，不看實際領到多少（供應不足時也照給）。
  - Guild Hall／City Hall 計算的建築不要求有殖民者（只有大型建築本身要）；可由 `Scoring.CountedBuildingsNeedColonist` 切換。
  - Craftsman 特權可選的貨種 = 公式產量 > 0 的貨種（即使供應區已空，那時只是拿不到）。
  - 倉庫保留：玩家一律完整保留 min(倉庫可保留種類數, 持有種類數) 種（保留更多不會變差），再選 1 桶；引擎不提供「少保留」的選項。
  - Hacienda 盲抽時牌疊已空：先把棄牌洗回再抽（規則只寫了翻牌時的洗牌）。
  - 市長階段是逐位玩家把全部殖民者拔起再放（先輪到的人先放）；結果與同時放置相同。
- 規則：隱藏資訊（對手 VP）只靠約定，沒有機制阻止策略讀取。
- 續跑（`--resume`）需要 `output.perGameRecords: true`；結果檔約 430 bytes／局（10 萬局約 43 MB）。
- 效能：4 核心約 21,000 局／秒（約 5,000 局／秒／核心，隨機玩家，一局約 500 個決策）。
- 隨機玩家下座位 3（玉米起手）勝率約 49%，座位 1、2 各約 24%；已驗證不是引擎不對稱（三家都改染料起手後各 33%）。
- 沒有 lint 工具（`dotnet format --verify-no-changes` 可用）；Dashboard 尚未建立。
- SessionStart hook 只有合併到預設分支後，新 session 才會自動套用；hook 的「dotnet 不存在時 apt 安裝」分支在已安裝的容器中無法重測。
- `builds.dotnet.microsoft.com` 被網路代理擋住，`dotnet-install.sh` 不可用，只能用 apt 安裝 .NET。
- 開發分支依 session 指定為 `claude/cool-cerf-xsrphb`；你提供的 Git 規則原文寫的是 `claude/trusting-hopper-wk15uy`，我已改成本 repo 的分支，請確認。

## 想法

- 結果檔過大時，`games` 另寫 JSONL，主檔只放 summary。
- Dashboard 內建單局回放檢視（Runner 的 `--replay N` 已能輸出決策記錄）。
