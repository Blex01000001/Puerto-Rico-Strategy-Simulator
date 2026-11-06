# Puerto Rico Strategy Simulator

開始新工作前先讀 `docs/TODO.md`。

目的：用大量模擬找出「波多黎各」桌遊的強策略。這不是可玩遊戲，沒有玩家介面。
規則來源：`rules.md`（唯一依據；有歧義先問，不自行假設）。**目前 rules.md 資料大致齊備（設置、職業、建築、階段細節、終局計分，另有待確認項目見 TODO），repo 內還沒有任何程式碼。**

## 檔案地圖（先看這裡決定要讀哪個檔案）
依任務從這張表找到要讀的檔案，只讀相關檔案，不要整個 repo 掃過。表上沒有的檔案通常不需要動；新增或搬移檔案時同步更新這張表。

| 路徑 | 用途 | 狀態 |
|---|---|---|
| `docs/TODO.md` | 目前狀態：待辦、已知問題、想法；每次 commit 時同步更新 | 已有 |
| `rules.md` | 遊戲規則唯一依據 | 資料齊備，仍有待確認項目（見 TODO） |
| `PuertoRico.sln`, `Directory.Build.props` | 解決方案與共用建置設定（net8.0、Nullable） | 規劃中 |
| `Engine/Game/` | 狀態、動作、規則（GetLegalActions/Apply）、Setup、計分、靜態表 | 規劃中 |
| `Engine/Strategies/` | `IStrategy`、隨機玩家、策略註冊（預留 RuleBased/、Mcts/） | 規劃中 |
| `Engine/Simulation/` | 設定/結果模型、單局執行器、批次模擬器、種子衍生 | 規劃中 |
| `Engine/Events/` | 事件記錄（大量模擬用 NullSink，回放用 ListSink） | 規劃中 |
| `Runner/` | 主控台入口：命令列、Ctrl+C、進度、寫結果檔 | 規劃中 |
| `Dashboard/` | Blazor Web App (Interactive Server)：設定、檢視、圖表 | 第一階段不做 |
| `Tests/` | xUnit | 規劃中 |

## 專案結構與相依方向（.NET 8，PuertoRico.sln）
- Engine：規則引擎 + 策略 + 模擬器；Runner：批次模擬共用入口（本機與 RunPod）；Dashboard：只負責設定／檢視／圖表；Tests：xUnit。
- Runner、Dashboard、Tests 只參考 Engine。Engine 不得引用 Blazor、任何 UI 或 Windows 專用 API。
- 不使用 EF Core；存資料用 JSON 檔，或 SQLite + Dapper。
- 路徑一律用 `Path.Combine`，不寫死 Windows 路徑。

## 建置、測試、Runner
```bash
dotnet build -c Release
dotnet test -c Release
dotnet run -c Release --project Runner -- --config config.json --games 100000 --out result.json
```
- 雲端容器預設沒有 dotnet：用 `apt-get update && apt-get install -y dotnet-sdk-8.0`（8.0.133 已驗證可 build/test/NuGet restore）。`builds.dotnet.microsoft.com` 被擋，`dotnet-install.sh` 不可用。
- Runner 長時間執行定期寫中間結果、回報進度、Ctrl+C 後寫出目前結果再結束。

## 常見任務怎麼改
常做的修改照這裡的步驟走，不用重新調查。格式：任務 → 改哪些檔案／函式 → 注意事項 → 怎麼驗證。做完一種新類型的修改，若之後可能重複，就補一條進來。

（尚無；程式碼建立後補上，例如「新增建築」「新增職業」「新增策略」「改設定/結果 JSON 欄位」。）

## 架構決策（不要改回去）
已討論過、刻意選擇的設計。真的認為該推翻，先提出來討論（標【先討論】），不要直接改。格式：決策 — 原因 — 不要做什麼。

- Engine 零 UI/Windows 相依 — 要能在 RunPod Linux、無 Blazor/VS 環境獨立執行 — 不要讓 Engine 引用 Dashboard 或 UI 套件。
- 設定與結果皆為 JSON，Runner 與 Dashboard 共用同一份格式（定義在 `Engine/Simulation/`），含 `schemaVersion` — 兩端不分歧、可匯入 — 不要各自定義格式。
- 策略介面固定為 `GameAction ChooseAction(GameState state, IReadOnlyList<GameAction> legalActions)`；隨機、手寫規則、MCTS 共用 — 不要為某個策略另開介面。
- 每個決策點 = 目前狀態 + 合法動作清單；引擎提供 Clone / GetLegalActions / Apply / IsOver / Score — 不要讓策略直接改狀態。
- GameState 只含數值與固定長度陣列（無 List/Dictionary/字串）— Clone 要快（MCTS）— 不要在狀態中放參考型別集合。
- 平行用 `Parallel.For`；大量模擬關閉事件記錄 — 效能 — 不要在批次模擬中開 event log。
- 第一階段範圍：3 人基礎版、無擴充；策略與 Dashboard 之後再做 — 不要提前實作。
- 以下為規劃建議，**待使用者確認前不算定案**（見 TODO）：每局種子由 (masterSeed, gameIndex) 衍生、座位預設輪換。

## 亂數種子規則
- 同一份設定與種子，結果必須可完整重現。
- 每個執行緒／每局使用獨立的 Random；禁止共享或靜態 Random、`Random.Shared`、以時間當亂數來源。
- MCTS 只用模擬次數，不用時間限制（時間限制會破壞重現性）。
- 建議（待確認）：gameSeed = SplitMix64(masterSeed, gameIndex)，使結果與執行緒數無關。

## 設計規範
- 規則數字（張數、費用、VP 等）集中在靜態表，不散落在邏輯裡；每條規則的測試註明 rules.md 出處。
- 測試：每條規則一個情境測試；隨機局不變量檢查（貨物／殖民者守恆、金幣不為負、格數上限、合法動作不為空）；Clone 一致性；同種子重現；golden file 回歸。
- 規則有歧義時先問使用者，不自行假設。

## 容易踩的雷
看起來像錯誤或可簡化、但其實是刻意或改了會壞的地方。修改相關檔案前先看這節。格式：位置 — 現象 — 為什麼不能動／該怎麼處理。

- 環境 — 新 session 沒有 dotnet — 需先 apt 安裝（見上）；容器是暫時的。
- 種植園牌堆（規劃）— 洗好後存在 GameState，抽牌是確定性的 — MCTS 會偷看牌序，之後做 MCTS 時須在策略層對未翻開的牌重洗（determinization）。

## 使用者的工作習慣
- 回覆用繁體中文；commit 訊息用英文。
- 訊息常分「待處理事項」（直接改）與「待討論事項」（只分析、給建議，不改程式）。
- 改輸出格式（設定／結果 JSON 欄位）、引入建置工具、改架構前先問。

## Git 規則
- 開發分支 `claude/cool-cerf-xsrphb`。它的 PR 合併後，新工作先從最新 `main` 重開：
  `git fetch origin main && git checkout -B claude/cool-cerf-xsrphb origin/main`（推送用 `--force-with-lease`）。
- 使用者說「合併到 main」時：用 GitHub MCP 工具建立 PR 再 merge（`expectedHeadSha` 用完整 40 字元 SHA）。
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
