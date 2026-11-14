# Puerto Rico Strategy Simulator

目的：用大量模擬找出「波多黎各」桌遊的強策略。不是可玩遊戲，沒有玩家介面。
範圍：3 人與 4 人基礎版（`players: 3|4`，4 人局多 Prospector），無擴充、不做 5 人局。
規則唯一依據：`rules.md`（有歧義先問，不自行假設；引擎採用的詮釋列在 `docs/TODO.md`「已知問題」）。

開始新工作前先讀 `docs/TODO.md`。

## 讀檔規則（省 token）
- 先用下面的地圖決定讀哪裡，只讀相關檔案，不要整個 repo 掃過。
- `Engine/CLAUDE.md`、`Dashboard/CLAUDE.md` 有該資料夾的細部檔案地圖、改法、架構決策與雷；讀到該資料夾的檔案時會自動載入，動手前不用另外找。
- `docs/strategy-analysis.md` 很長（60 KB 以上）：先 `grep -n '^#' docs/strategy-analysis.md` 找節，再只讀那一節。
- `results/` 的結果檔（每個數十 MB）不要用 Read 打開；要數字就用 Runner 的輸出、`tools/` 的工具或 `python3`／`jq` 只取摘要欄位。
- 實驗設定（`tournaments/`、`sweeps/`、`mcts/`）各資料夾做了什麼：查 `docs/experiments.md`，不用逐一打開設定檔。
- 新增或搬移檔案時，同步更新對應的地圖（根目錄的改這裡，Engine／Dashboard 內的改各自的 `CLAUDE.md`）。

## 地圖
| 路徑 | 用途 |
|---|---|
| `README.md` | 給第一次看的人：目的、主要結論（數字來自分析文件，分析更新時同步）、快速開始 |
| `docs/TODO.md` | 待辦、已知問題、想法（目前狀態） |
| `docs/strategy-analysis.md` | 策略分析與結論（第 0 節座位偏差、1～2 對戰、3～4 調參、5 MCTS、7 Wharf／壟斷、8 同分、9 陪練） |
| `docs/experiments.md` | 實驗設定索引：`tournaments/`、`sweeps/round*`、`mcts/` 各是什麼、怎麼重跑 |
| `rules.md` | 遊戲規則（第 1～6 節 3 人局，第 7 節 4 人局差異） |
| `Engine/` | 規則引擎 `Game/`、策略 `Strategies/`、模擬與統計 `Simulation/`、事件 `Events/`；細節見 `Engine/CLAUDE.md` |
| `Runner/Program.cs` | 命令列：`--config --games --seed --threads --out --resume --replay --sweep --dump-positions --dump-rate` |
| `Dashboard/` | Blazor Web App（八頁：HOME、模擬、結果、總覽、比較、回放、參數掃描、設定檔）；細節見 `Dashboard/CLAUDE.md` |
| `Tests/` | xUnit，只參考 Engine：`SetupTests`、`SettlerMayorTests`、`BuilderCraftsmanTests`、`TraderCaptainTests`、`EndGameScoringTests`、`SimulationTests`（fuzz／重現／續跑／取消）、`StrategyTests`、`ValueModelTests`（推論與 Python 一致、特徵視角、dump 可重現；固定資料在 `Tests/Data/`）；情境用 `Tests/Sc.cs`（`Sc.Start` 指定總督與職業） |
| `ml/` | MCTS 的學習型價值函數：Python 訓練（LightGBM、NumPy MLP）、產生資料的設定、模型檔；流程見 `ml/README.md`（資料檔放 `results/ml/`） |
| `tools/tiestats/`、`tools/sparring/` | 分析工具，不在 `PuertoRico.sln`（改 Engine 後要另外 `dotnet build -c Release tools/<名稱>`）；用法寫在各自 `Program.cs` 開頭 |
| `config*.json` | 設定檔範例（Runner 與 Dashboard 共用格式） |
| `PuertoRico.sln`、`Directory.Build.props` | net8.0、Nullable、TreatWarningsAsErrors（csproj 內不要重複設；新程式碼要零警告） |
| `.claude/` | SessionStart hook：雲端 session 自動安裝 .NET 8 並 restore |

## 指令
```bash
dotnet build -c Release
dotnet test -c Release
dotnet run -c Release --project Runner -- --config config.example.json --games 100000 --out results/x.json   # 加 --sweep 跑參數掃描、--resume 續跑、--replay N 看第 N 局
dotnet run -c Release --project Dashboard   # http://localhost:5080，讀 results/
```
- 沒有 `dotnet` 時：`apt-get update && apt-get install -y dotnet-sdk-8.0`（`dotnet-install.sh` 被網路擋住，不可用）。
- 指令輸出很長時接 `| tail` 或 `grep`，只看需要的行。

## 全專案規則（不要改回去；要推翻先討論）
- 相依方向：Runner、Dashboard、Tests 只參考 Engine；Engine 不得引用 Blazor、UI 或 Windows 專用 API（要能在 RunPod Linux 獨立執行）。
- 設定與結果都是 JSON，格式只定義在 `Engine/Simulation/`，Runner 與 Dashboard 共用，含 `schemaVersion`。不使用 EF Core。
- 路徑一律 `Path.Combine`。
- 重現性：同設定同種子結果必須完全相同；禁止共享／靜態 Random、`Random.Shared`、以時間當亂數或限制（MCTS 只用模擬次數）。
- 比較策略用 `seatOrder: random`（預設）或 `balanced`，不要用 `rotate`／`fixed` 的單一排列下結論（同一桌勝率可差 20 個百分點以上）；統計看策略不看座位。
- `results/` 已被 `.gitignore` 忽略：絕對不要 `git add -f`；`git add -A` 之前先看 `git status`。
- 規則數字集中在靜態表；每條規則一個情境測試並註明 rules.md 節次。

## 使用者的工作習慣
- 回覆用繁體中文；commit 訊息用英文。
- 訊息常分「待處理事項」（直接改）與「待討論事項」（只分析、給建議，不改程式）。
- 改輸出格式（設定／結果 JSON 欄位）、引入建置工具、改架構前先問。
- 做完一種之後可能重複的新類型修改，就在對應的 `CLAUDE.md` 補一條改法；發現新的雷也補上。

## Git 規則
- 開發分支 `claude/cool-cerf-xsrphb`。它的 PR 合併後，新工作先從最新 `main` 重開：
  `git fetch origin main && git checkout -B claude/cool-cerf-xsrphb origin/main`（推送用 `--force-with-lease`）。
- 使用者說「合併到 main」時：用 GitHub MCP 工具建立 PR 再 merge（`expectedHeadSha` 用完整 40 字元 SHA）。`create_pull_request` 可能回 502 但其實已建立：重試前先 `list_pull_requests`（`state: open`）。
- 改寫 main 歷史只有使用者明確說「改寫 main 歷史」才做；先備份分支、驗證檔案樹不變，用 `--force-with-lease=<分支>:<舊SHA>`。
- 每完成一個獨立的修改就 commit；過去的修改用 `git log` 查。

## TODO 維護（`docs/TODO.md`）
- 每次 commit 一併更新：做完的刪掉、新發現的加進去、不適用的刪掉或改寫。
- 只記目前狀態，不寫歷史；每項一行為主。
- 使用者說「做待辦 N」以這份檔案的編號為準；整理時可重新編號。

## Commit 後的回報
每次 commit 並 push 後，回覆包含三段，內容與 `docs/TODO.md` 一致：
1. **已改善項目／問題**
2. **尚待改善項目／問題、已知問題**
3. **建議改善方向或功能**
