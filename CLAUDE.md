# Puerto Rico Strategy Simulator

開始新工作前先讀 `docs/TODO.md`。

目的：用大量模擬找出「波多黎各」桌遊的強策略。這不是可玩遊戲，沒有玩家介面。
規則來源：`rules.md`（唯一依據；有歧義先問，不自行假設）。**目前 rules.md 資料齊備（設置、職業、建築、階段細節、終局計分、4 人局差異；引擎採用的幾項詮釋見 TODO「已知問題」）；第一階段引擎、隨機玩家、批次模擬與 Runner 已完成並有測試；手寫策略已有玉米出貨流、玉米轉菸草／咖啡流、港口流、建築優先流，另有 MCTS 策略（`mcts`）；3、4 人局皆支援；Dashboard（左側導覽：HOME 介紹頁、模擬、結果…）已有 HOME、模擬、結果、總覽（多個結果檔彙整，含信賴區間與兩兩對戰矩陣）、比較（A/B 兩個結果檔並排）、回放（重打結果檔中的某一局，可逐步看盤面：種植園、建築、貨物、貨船）、模擬（直接在 Dashboard 選策略並執行一般對戰或參數掃描）、參數掃描、設定檔八頁。**

## 檔案地圖（先看這裡決定要讀哪個檔案）
依任務從這張表找到要讀的檔案，只讀相關檔案，不要整個 repo 掃過。表上沒有的檔案通常不需要動；新增或搬移檔案時同步更新這張表。

| 路徑 | 用途 | 狀態 |
|---|---|---|
| `README.md` | 給第一次看的人：專案目的、主要結論（數字來自 `docs/strategy-analysis.md`，分析更新時同步）、快速開始、Dashboard 功能 | 已有 |
| `docs/TODO.md` | 目前狀態：待辦、已知問題、想法；每次 commit 時同步更新 | 已有 |
| `rules.md` | 遊戲規則唯一依據（第 1～6 節 3 人局，第 7 節 4 人局差異） | 資料齊備，沒有待確認的規則問題 |
| `PuertoRico.sln`, `Directory.Build.props` | 解決方案與共用建置設定（net8.0、Nullable、TreatWarningsAsErrors） | 已有 |
| `.claude/hooks/session-start.sh`, `.claude/settings.json` | SessionStart hook：雲端 session 自動安裝 .NET 8 並 restore | 已有 |
| `config.example.json`、`config.4p.example.json`、`config.sweep.example.json`、`config.corn-vs-random.json`、`config.strategies-compare.json` | 設定檔範例（Runner 與 Dashboard 共用格式）；`corn-vs-random` 為 corn-shipper 對兩個隨機玩家，`strategies-compare` 為三個手寫原型互打 | 已有 |
| `Engine/Game/` | `GameState`（可複製狀態）、`GameAction`、`Rules.cs`（GetLegalActions/Apply/Advance）、`Rules.<階段>.cs`（Settler/Mayor/Builder/Craftsman/Trader/Captain 的 Fill+Apply）、`Setup.cs`、`Scoring.cs`、`Buildings.cs`/`GameConstants.cs`（靜態表）、`Invariants.cs` | 已有 |
| `Engine/Strategies/` | `IStrategy`、`IDecisionExplainer`（選用：MCTS 回報每步搜尋摘要給回放，`IGameEventSink.OnSearch`）、`RandomStrategy`、`StrategyRegistry`（名稱：`random`、`corn-shipper`、`corn-to-premium`、`harbor-rush`、`build-first`、`cheap-engine`、`guided-random`、`mcts`，或 `rule-based`＋`params.profile`）；`RuleBased/HeuristicStrategy.cs`（共用打分基底：每個選擇打分數取最高，子類別覆寫掛鉤）、`CornShipperStrategy`（玉米出貨流）、`CornToPremiumStrategy`（前期玉米、中後期菸草／咖啡）、`HarborRushStrategy`（先蓋港口再靠港口出貨，後期加 Wharf）、`BuildFirstStrategy`（建築優先：採石場折扣、混合經濟換金幣、依終局加成挑大型建築）、`CheapEngineStrategy`（便宜引擎流：由 MCTS 行為分析而來，早買便宜 1 分建築、少量種植園、頻繁出貨）；`GuidedRandomStrategy`（按動作種類加權的隨機）；`Mcts/MctsStrategy.cs`（UCT 樹搜尋，`params.simulations`／`rolloutStrategy`／`rolloutRounds`／`exploration`，只用模擬次數）；手寫策略的預設參數依玩家數分開：子類別覆寫 `Configure(players)`，用 `Param(名稱, players, 3人預設, 4人預設)` 讀 | 隨機、四個手寫原型與 MCTS 已有 |
| `Engine/Simulation/` | `ResultAnalysis.cs`（Dashboard 用的統計：勝率與信賴區間、分數構成與分佈、名次矩陣、每個建築的取得率與勝率、港口取得回合）、`ResultComparison.cs`（兩份分析結果依策略名稱並排：勝率差與顯著性）、`TournamentOverview.cs`（多個結果檔依玩家數彙整每個策略的平均勝率與信賴區間、兩兩對戰矩陣）、`SimulationConfig`、`Sweep.cs`（參數掃描：設定、`SweepRunner`、結果）、`SimulationResult`（含摘要；`PlayerRecord` 有建築清單 `Buildings`／購買回合 `BuiltRounds`、期末種植園 `Tiles`、金幣、出貨次數，舊檔這些欄位為 null）、`SeedDeriver`、`GameRunner`（單局＋座位分配）、`BatchSimulator`（Parallel／checkpoint／取消／續跑） | 已有 |
| `Engine/Events/` | 事件記錄：`NullEventSink`（大量模擬）、`ListEventSink`（回放） | 已有 |
| `Runner/Program.cs` | 命令列：`--config --games --seed --threads --out --resume --replay --sweep` | 已有 |
| `Tests/` | xUnit（含 `StrategyTests`）：`SetupTests`、`SettlerMayorTests`、`BuilderCraftsmanTests`、`TraderCaptainTests`、`EndGameScoringTests`、`SimulationTests`（fuzz／重現／續跑／取消） | 已有 |
| `Dashboard/` | Blazor Web App (Interactive Server，只參考 Engine)：`Services/AppState.cs`（載入結果／掃描檔）、`Services/SimulationService.cs`（背景執行 `BatchSimulator`、進度、取消）、`Services/SnapshotEventSink.cs`（回放用，保存每個決策前的狀態、動作與 MCTS 搜尋摘要）、`Services/ActionText.cs`（把一步動作寫成中文說明：付多少錢、賣多少、出貨得幾分）、`Components/MctsSearch.razor`（MCTS 每個合法動作的訪問次數與平均報酬）、`Services/StrategyInfo.cs`（HOME 與模擬頁「流派介紹」的行為規則與可調參數文字）、`Services/Palette.cs`（策略顏色與名稱）、`Components/Charts/`（純 SVG 圖表：BarChart／StackedBars／LineChart）、`Components/Pages/`（Home `/`、Results `/results`、Overview、Compare、Replay、Simulate、Sweep、Config）；`AppState.ReadConfigAsync` 只讀結果／掃描檔的 config（跳過逐局記錄，大檔很快），模擬頁的「用結果檔當範本」與結果頁「用這份設定再模擬」（`AppState.SetTemplate`）、回放頁都用它；畫面上的路徑一律用 `AppState.DisplayPath`／`Scrub` 顯示成相對專案根目錄，不顯示機器上的完整路徑、`Components/FilePicker.razor`、`Components/BoardView.razor`（回放盤面）、`wwwroot/favicon.svg`（瀏覽器圖示）、`wwwroot/app.css`（色票 token；只有一套扁平深色主題，Steam／Discord 風，沒有淺色模式） | 已有 |

## 專案結構與相依方向（.NET 8，PuertoRico.sln）
- Engine：規則引擎 + 策略 + 模擬器；Runner：批次模擬共用入口（本機與 RunPod）；Dashboard：只負責設定／檢視／圖表；Tests：xUnit。
- Runner、Dashboard、Tests 只參考 Engine（Dashboard 的「模擬」頁直接呼叫 Engine 的 `BatchSimulator`，結果寫進結果資料夾）。Engine 不得引用 Blazor、任何 UI 或 Windows 專用 API。
- 不使用 EF Core；存資料用 JSON 檔，或 SQLite + Dapper。
- 路徑一律用 `Path.Combine`，不寫死 Windows 路徑。
- 策略分析與結論：`docs/strategy-analysis.md`；對戰設定在 `tournaments/`（`tournaments/run.sh` 重跑，結果進 git 忽略的 `results/`），調參設定在 `sweeps/`（4 人局第一輪）、`sweeps/round2/`、`sweeps/3p/`（3 人局，每個目標對三種對手組合）、`sweeps/round3/`、`sweeps/3p-round3/`、`sweeps/round4/`（cheap-engine）、`sweeps/round5/`（座位 random 重掃）；MCTS 實驗設定在 `mcts/`。

## 建置、測試、Runner
```bash
dotnet build -c Release
dotnet test -c Release
dotnet run -c Release --project Runner -- --config config.json --games 100000 --out result.json
dotnet run -c Release --project Dashboard   # http://localhost:5080，讀 results/ 資料夾（見 appsettings Dashboard:ResultsDirectory）
```
- 雲端 session 由 SessionStart hook 自動安裝 .NET 8 並 restore（只在 `CLAUDE_CODE_REMOTE=true` 時執行；hook 需合併進預設分支後新 session 才會生效）。手動安裝：用 `apt-get update && apt-get install -y dotnet-sdk-8.0`（8.0.133 已驗證可 build/test/NuGet restore）。`builds.dotnet.microsoft.com` 被擋，`dotnet-install.sh` 不可用。
- Runner 長時間執行定期寫中間結果、回報進度、Ctrl+C 後寫出目前結果再結束。

## 常見任務怎麼改
常做的修改照這裡的步驟走，不用重新調查。格式：任務 → 改哪些檔案／函式 → 注意事項 → 怎麼驗證。做完一種新類型的修改，若之後可能重複，就補一條進來。

- **改／加規則**：先改 `rules.md` → 改 `Engine/Game/Rules.<階段>.cs` 的 `Fill*`（列合法動作）與 `Apply*`（執行）；靜態數字改 `Buildings.cs`／`GameConstants.cs` → 在對應 `Tests/*Tests.cs` 加情境測試並註明 rules.md 節次 → `dotnet test -c Release`（fuzz 測試會檢查不變量）。新增動作種類時同步改 `ActionType`、`GameAction.ToString`。
- **加手寫策略**：新類別繼承 `RuleBased/HeuristicStrategy.cs`，只覆寫要改的掛鉤（`TileValue`、`BuildingWanted`、`SlotValue`、各角色價值…），在 `StrategyRegistry` 註冊並加進 `rule-based` 的 profile 清單，參考 `HarborRushStrategy.cs`；測試放 `Tests/StrategyTests.cs`（用 `Sc.Start` 建情境，檢查它選的動作）。
- **加／改策略後**：同步 `Dashboard/Services/StrategyInfo.cs`（流派介紹：規則與參數預設值），否則 HOME 與模擬頁的說明會過時。
- **加其他策略**：新檔 `Engine/Strategies/XStrategy.cs` 實作 `IStrategy`（座位 = `state.Actor`，亂數只用工廠給的 seed，不得讀對手 `VpChips`）→ 在 `StrategyRegistry.Factories` 註冊名稱 → 設定檔 `seats[].strategy` 填該名稱，參數放 `params` → 加測試（至少能跑完 100 局且不丟例外）。
- **改設定／結果 JSON 欄位**（先問使用者）：`SimulationConfig.cs`／`SimulationResult.cs`；新增欄位給預設值以相容舊檔，破壞性改動遞增 `SchemaVersion`；同步 `config.example.json` 與 `BatchSimulator.EnsureCompatible`（續跑比對的欄位）。
- **參數掃描**：設定檔加 `sweep: { target: "<seat id>", gamesPerPoint, parameters: { 名稱: [值…] } }`（只掃數值型 `params`，格點為笛卡兒積），`dotnet run -c Release --project Runner -- --config config.sweep.example.json --sweep --out sweep.json`；每個格點用同一個主種子（共用隨機抽牌，差異雜訊較小），只比較 target 座位的勝率（附 95% 信賴區間）與平均分，對手固定。新增可掃參數 = 在策略建構子用 `StrategyRegistry.GetDouble` 讀 `params`。
- **改 Dashboard 圖表**：統計放 `Engine/Simulation/ResultAnalysis.cs`（加單元測試），畫圖用 `Components/Charts/` 的元件（純 SVG，不引入 JS 套件）；顏色一律用 CSS 變數（`app.css` 的 `--series-N`，策略顏色走 `Palette.Color`，顏色跟策略不跟排名）；每張圖附表格檢視；在 Razor 的 `@for` 裡寫 SVG `<text>` 要包在 `<g>` 裡（Razor 的 `<text>` 是保留標籤）；改完用 Playwright 截圖看（淺色與深色）。
- **跑模擬**：`dotnet run -c Release --project Runner -- --config config.example.json --games 100000 --out result.json`；Ctrl+C 會寫出 `cancelled` 結果，`--resume` 續跑（需 `perGameRecords: true`）；`--replay N` 輸出第 N 局的決策記錄。

## 架構決策（不要改回去）
已討論過、刻意選擇的設計。真的認為該推翻，先提出來討論（標【先討論】），不要直接改。格式：決策 — 原因 — 不要做什麼。

- Engine 零 UI/Windows 相依 — 要能在 RunPod Linux、無 Blazor/VS 環境獨立執行 — 不要讓 Engine 引用 Dashboard 或 UI 套件。
- 設定與結果皆為 JSON，Runner 與 Dashboard 共用同一份格式（定義在 `Engine/Simulation/`），含 `schemaVersion` — 兩端不分歧、可匯入 — 不要各自定義格式。
- 策略介面固定為 `GameAction ChooseAction(GameState state, IReadOnlyList<GameAction> legalActions)`；隨機、手寫規則、MCTS 共用 — 不要為某個策略另開介面。
- 每個決策點 = 目前狀態 + 合法動作清單；引擎提供 Clone / GetLegalActions / Apply / IsOver / Score — 不要讓策略直接改狀態。
- GameState 只含數值與固定長度陣列（無 List/Dictionary/字串）— Clone 要快（MCTS）— 不要在狀態中放參考型別集合。
- 平行用 `Parallel.For`；大量模擬關閉事件記錄 — 效能 — 不要在批次模擬中開 event log。
- 狀態推進：`Apply` 之後自動推進到下一個真正的決策——沒有動作或只剩 `Pass` 的人直接略過 — 策略不會被問無意義的問題 — 不要在策略端重做略過邏輯。唯一合法動作（非 Pass）由 `GameRunner` 依 `options.autoAdvanceForced` 直接套用。
- Mayor 放置採「依 slot 非遞減順序逐一放置」，並剪掉無法放滿的選項 — 每種分配只對應一條動作序列，避免排列重複 — 不要改成任意順序。
- 牌疊以各種類張數＋`RngState` 表示，不存牌序 — Clone 小、洗牌可重現 — 不要在狀態內存洗好的牌陣列。
- 範圍：3 人與 4 人基礎版（`players: 3|4`，4 人局多一個 Prospector 職業），無擴充、不做 5 人局 — 不要加擴充內容。
- 每局種子由 (masterSeed, gameIndex) 衍生 — 結果與執行緒數、分工方式無關，且 `--resume` 容易 — 不要改成「每執行緒一個 Random」。
- 設定 `seatOrder` 預設 `random`（每局隨機排座位），另有 `balanced`（3 人 6 種、4 人 24 種排列輪流，局數是 6／24 的倍數時每個策略坐每個座位、鄰座的次數完全相等）；`rotate` 與 `fixed` 不建議 — 3 人局有座位優勢，且「誰坐在誰旁邊」會讓同一桌勝率差 20 個百分點以上；統計以「策略」而非座位歸類 — 不要預設固定座位或輪換。
- 隱藏資訊（對手 VP 籌碼）：策略介面照傳完整 `GameState`，約定策略**不得讀取對手 VP**；MCTS 內部需要完整狀態 — 簡單且不增加 Clone 成本 — 不要為此另做遮罩副本或另開介面。

## 亂數種子規則
- 同一份設定與種子，結果必須可完整重現。
- 每個執行緒／每局使用獨立的 Random；禁止共享或靜態 Random、`Random.Shared`、以時間當亂數來源。
- MCTS 只用模擬次數，不用時間限制（時間限制會破壞重現性）。
- gameSeed = SplitMix64(masterSeed, gameIndex)；策略（含 MCTS）的亂數由 (gameSeed, seat) 衍生，結果與執行緒數無關。

## 設計規範
- 規則數字（張數、費用、VP 等）集中在靜態表，不散落在邏輯裡；每條規則的測試註明 rules.md 出處。
- 測試：每條規則一個情境測試；隨機局不變量檢查（貨物／殖民者守恆、金幣不為負、格數上限、合法動作不為空）；Clone 一致性；同種子重現；golden file 回歸。
- 規則有歧義時先問使用者，不自行假設。
- 座位 ID（固定 1～3 或 1～4，起始種植園綁座位）與「當前總督」指標分開追蹤；金幣無上限，貨物與殖民者有嚴格數量上限。

## 容易踩的雷
看起來像錯誤或可簡化、但其實是刻意或改了會壞的地方。修改相關檔案前先看這節。格式：位置 — 現象 — 為什麼不能動／該怎麼處理。

- 環境 — 容器是暫時的，dotnet 靠 SessionStart hook 安裝（hook 已在 main）— 若新 session 沒有 `dotnet`，手動 apt 安裝（見上）。
- 專案檔 — `Directory.Build.props` 已設 net8.0／Nullable／TreatWarningsAsErrors，csproj 內不要重複設 — 警告即錯誤，新增程式碼要零警告。
- `GameState.RngState` — 抽種植園時才推進亂數 — 複製後兩份狀態會抽到相同的牌；MCTS 的每次 rollout 必須先 `ReseedRng(新種子)`，否則所有 rollout 看到同一個未來。
- `Rules.Apply` 之後的狀態一定停在下一個真實決策 — 不要自己迴圈略過 Pass；測試用 `Sc.Start`（`Tests/Sc.cs`）直接指定總督與職業來建情境。
- `seatOrder: rotate` — 保留固定的循環座位順序，同一桌換設定檔排列順序勝率差 20 個百分點以上（corn 23.8%／5.6%／2.3%）— 比較策略要用 `random`（預設）或 `balanced`，不要用 `rotate` 的單一排列下結論；第一到第三輪調參用的是 `rotate`，絕對勝率帶有這個偏差（`docs/strategy-analysis.md` 第 0 節）；MCTS 實驗（`mcts/`）已用 `balanced` 重做（A/B 成對比較也會受排列順序影響，重做後一個結論翻轉）。
- 隨機玩家下座位 3（玉米起手）勝率明顯偏高（約 49%）— 不是 bug：把三家起手都改成染料後三座位勝率各 33%；所以座位要輪流（預設 `seatOrder: random`），統計看策略而非座位。

- `results/` — 模擬輸出（10 萬局 70～90 MB）已被 `.gitignore` 忽略 — 絕對不要 `git add -f`；`git add -A` 之前先看 `git status`（曾誤把 390 MB 結果檔 commit 進 main，後來改寫歷史才清掉）。
- 手寫策略預設參數 — 依玩家數不同（`Param` 在第一次 `ChooseAction` 才解析，因為建構時還不知道人數）；`StrategyTests` 的情境多半是 3 人局，用到 4 人預設值（如 premium 的 `switchRound`、harbor 的 `harborReadyTiles`）時要明確傳參數或指定玩家數 — 設定檔明確寫的參數永遠優先。
- 玩家數 — 每位玩家的陣列固定開 4 個座位的大小，3 人局第 4 座位全是 0 — 迴圈、模數一律用 `s.PlayerCount`、`s.RoleCount`、`s.ShipCap`，不要用 `GameConstants` 的固定值；`GameConstants.XXX(players)` 是依人數查的函式。

## 使用者的工作習慣
- 回覆用繁體中文；commit 訊息用英文。
- 訊息常分「待處理事項」（直接改）與「待討論事項」（只分析、給建議，不改程式）。
- 改輸出格式（設定／結果 JSON 欄位）、引入建置工具、改架構前先問。

## Git 規則
- 開發分支 `claude/cool-cerf-xsrphb`。它的 PR 合併後，新工作先從最新 `main` 重開：
  `git fetch origin main && git checkout -B claude/cool-cerf-xsrphb origin/main`（推送用 `--force-with-lease`）。
- 使用者說「合併到 main」時：用 GitHub MCP 工具建立 PR 再 merge（`expectedHeadSha` 用完整 40 字元 SHA）。
- GitHub MCP 的 `create_pull_request` 可能回 502 但其實已建立 PR：重試前先 `list_pull_requests`（`state: open`）查有沒有，有就直接用那個 PR 編號合併。
- 改寫共用分支的歷史（force push main）只有使用者明確說「改寫 main 歷史」才做；做之前先備份分支、驗證最終檔案樹不變，用 `--force-with-lease=<分支>:<舊SHA>` 推送。
- 每完成一個獨立的修改就 commit。commit 訊息第一行簡述改了什麼，需要時空一行補充原因。
- 需要了解過去的修改時，用 `git log` 查詢。

## TODO 維護規則（`docs/TODO.md`）
- 每次 commit 時一併更新：做完的刪掉、新發現的加進去、不適用的刪掉或改寫。
- 只記目前狀態，不寫完成紀錄或歷史（歷史看 `git log`）；每項一行為主，保持精簡。
- 使用者說「做待辦 N」時以這份檔案的編號為準；整理時可重新編號。

## Commit 後的回報規則
每次 commit 並 push 後，回覆必須包含以下三段，內容要和 `docs/TODO.md` 一致：
1. **已改善項目／問題**：這次 commit 完成了什麼。
2. **尚待改善項目／問題、已知問題**：還沒做完的、發現但未處理的問題、已知限制。
3. **建議改善方向或功能**：之後可以考慮的改進或新功能。
