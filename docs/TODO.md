# TODO — 目前狀態

記錄專案目前的待辦、已知問題與想法。標記：【直接做】使用者點名就能動手；【先討論】會改架構／輸出格式／引入新工具或方向未定；【使用者】需使用者自己操作。維護規則見 `CLAUDE.md`。

## 待辦

1. 【先討論】策略調參與下一批原型：四個手寫原型（`corn-shipper`、`corn-to-premium`、`harbor-rush`、`build-first`，在 `Engine/Strategies/RuleBased/`，共用 `HeuristicStrategy`）已互打並分析（`docs/strategy-analysis.md`）。建議下一輪：用最強的 `build-first` 當固定對手再調其他三個（交替調參）、3 人局另外調一輪、重做「先有出貨量再蓋港口」的港口流與改進菸草／咖啡變現路徑。
2. 【先討論】MCTS 策略：模擬次數放設定 `params.simulations`；每次 rollout 用 `Clone()` ＋ `ReseedRng`；隱藏資訊不遮罩（約定不讀對手 VP）；rollout 策略可用隨機或手寫策略。
3. 【直接做】Dashboard 擴充：兩個結果檔並排比較（A/B）、讀多個結果檔的「對戰總覽」頁（像 `docs/strategy-analysis.md` 的組合表）、單局回放檢視（讀 `--replay` 輸出）。
4. 【直接做】RunPod 部署說明與發佈指令（`dotnet publish -c Release -r linux-x64`），寫進 CLAUDE.md；視需要加 `--summary-only` 之類的輸出選項。

## 已知問題／限制

- 規則中未明說、引擎採用的詮釋（請使用者確認，或提供反例）：
  - Factory 的金幣依「公式產量 > 0 的貨種數」計算，不看實際領到多少（供應不足時也照給）。
  - Guild Hall／City Hall 計算的建築不要求有殖民者（只有大型建築本身要）；可由 `Scoring.CountedBuildingsNeedColonist` 切換。
  - Craftsman 特權可選的貨種 = 公式產量 > 0 的貨種（即使供應區已空，那時只是拿不到）。
  - 倉庫保留：玩家一律完整保留 min(倉庫可保留種類數, 持有種類數) 種（保留更多不會變差），再選 1 桶；引擎不提供「少保留」的選項。
  - Hacienda 盲抽時牌疊已空：先把棄牌洗回再抽（規則只寫了翻牌時的洗牌）。
  - 市長階段是逐位玩家把全部殖民者拔起再放（先輪到的人先放）；結果與同時放置相同。
- 結果記錄不含「各職業被選次數」（Prospector 偏好等要另外統計）與「每個建築是否有派殖民者」。
- 規則：隱藏資訊（對手 VP）只靠約定，沒有機制阻止策略讀取。
- 續跑（`--resume`）需要 `output.perGameRecords: true`；結果檔約 700～900 bytes／局（10 萬局：3 人局約 70 MB、4 人局約 89 MB）；舊版本（沒有建築清單）的結果檔仍可在 Dashboard 檢視，但不能 `--resume`。
- 手寫策略的對戰結論見 `docs/strategy-analysis.md`；3 人與 4 人結果差很多（建築優先流 4 人局 46%、3 人局只有 17～42%），而參數只用 4 人局調。座位優勢仍在（4 人局座位 1／2／3／4 勝率約 17%／24%／37%／23%）。
- 引擎玩家數 3 或 4（`players`）；5 人局與擴充不支援。4 人局職業 Prospector 在手寫策略裡的估值很簡單（約等於 1 枚金幣）。
- 沒有 lint 工具（`dotnet format --verify-no-changes` 可用）。Dashboard 沒有自動化測試（Tests 只參考 Engine）；以 Playwright 截圖驗證過三個頁面（淺色／深色）。分析邏輯在 `Engine/Simulation/ResultAnalysis.cs`，有單元測試。
- Dashboard 會把整份結果檔讀進記憶體（10 萬局約 50 MB 沒問題，百萬局以上要改成只讀摘要），並可讀取伺服器上任意路徑：只在本機執行（預設綁 localhost:5080），不要對外開放。
- 效能：4 核心約 21,000 局／秒（約 5,000 局／秒／核心，隨機玩家，一局約 500 個決策）。
- 隨機玩家下座位 3（玉米起手）勝率約 49%，座位 1、2 各約 24%；已驗證不是引擎不對稱（三家都改染料起手後各 33%）。
- SessionStart hook 只有合併到預設分支後，新 session 才會自動套用；hook 的「dotnet 不存在時 apt 安裝」分支在已安裝的容器中無法重測。
- `builds.dotnet.microsoft.com` 被網路代理擋住，`dotnet-install.sh` 不可用，只能用 apt 安裝 .NET。

## 想法

- Dashboard：策略顏色目前依策略名稱固定對應前 5 個色票（藍、橘、青、黃、洋紅），超過要定義更多色票或改用小倍數圖。
- 參數掃描目前是網格搜尋、對手固定；可考慮多目標座位同時掃、或交替調參（調 A 對固定 B，再調 B 對新 A）。

- 結果檔過大時，`games` 另寫 JSONL，主檔只放 summary。
- Dashboard 內建單局回放檢視（Runner 的 `--replay N` 已能輸出決策記錄）。
