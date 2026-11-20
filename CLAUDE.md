# Puerto Rico Strategy Simulator

目的：用大量模擬找出「波多黎各」桌遊的強策略。不是可玩遊戲，沒有玩家介面。
範圍：3 人與 4 人基礎版（`players: 3|4`，4 人局多 Prospector），無擴充、不做 5 人局。
規則唯一依據：`rules.md`（有歧義先問，不自行假設；引擎採用的詮釋列在 `docs/TODO.md`「已知問題」）。

開始新工作前先讀 `docs/TODO.md`。

## 讀檔規則（省 token）
- 先用下面的地圖決定讀哪裡，只讀相關檔案，不要整個 repo 掃過。
- `Engine/CLAUDE.md`、`Dashboard/CLAUDE.md`、`ml/CLAUDE.md` 有該資料夾的細部檔案地圖、改法、架構決策與雷；讀到該資料夾的檔案時會自動載入，動手前不用另外找。
- `docs/strategy-analysis.md` 很長（60 KB 以上）：先 `grep -n '^#' docs/strategy-analysis.md` 找節，再只讀那一節。
- `results/` 的結果檔（每個數十 MB）不要用 Read 打開；要數字就用 Runner 的輸出、`tools/` 的工具或 `python3`／`jq` 只取摘要欄位。
- 實驗設定（`tournaments/`、`sweeps/`、`mcts/`）各資料夾做了什麼：查 `docs/experiments.md`，不用逐一打開設定檔。
- 新增或搬移檔案時，同步更新對應的地圖（根目錄的改這裡，Engine／Dashboard 內的改各自的 `CLAUDE.md`）。

## 地圖
| 路徑 | 用途 |
|---|---|
| `README.md` | 給第一次看的人：目的與可重現性、MCTS＋GBDT／MLP 架構、訓練流程、模型概況（數字來自 `docs/models.md`／分析文件第 10 節，更新時同步；目前是規則版本 1 的數字）、手寫策略、快速開始（英文版待翻） |
| `docs/TODO.md` | 待辦、已知問題、想法（目前狀態） |
| `docs/strategy-analysis.md` | 策略分析與結論（第 0 節座位偏差、1～2 對戰、3～4 調參、5 MCTS、7 Wharf／壟斷、8 同分、9 陪練、10 學習型價值函數，10.4 資料局數與模型大小） |
| `docs/versions.json` | 版本控管清單：規則版本、引擎版本、特徵版本、資料格式版本與每個策略的策略版本，各自的版本號、commit 與每個版本的修改內容（兩個 UI 的「版本控管」頁讀它；規則見下面「版本與 hash」） |
| `docs/rules-interpretations.md` | 規則詮釋確認清單（TODO 8(a)）：六條引擎自行採用的詮釋，附規則原文、做法與例子，等使用者確認 |
| `i18n/` | UI 文字表：`ml.<語言>.json`（ML UI，`ml/i18n.py` 讀）、`dash.<語言>.json`（Dashboard，`Dashboard/Services/Loc.cs` 讀）；語言 `en`（預設）、`zh-TW`；`ml/tests/test_i18n.py` 檢查 |
| `docs/models.md` | 局面估值模型的研發紀錄與目前狀況（每個模型的資料、勝率、狀態；新增正式模型時補一列） |
| `docs/runpod.md` | RunPod：開哪種 pod、第一次設定、SSH 通道、長時間工作、把模型帶回本機、費用、重現性 |
| `docs/experiments.md` | 實驗設定索引：`tournaments/`、`sweeps/round*`、`mcts/` 各是什麼、怎麼重跑 |
| `rules.md` | 遊戲規則（第 1～6 節 3 人局，第 7 節 4 人局差異） |
| `Engine/` | 規則引擎 `Game/`、策略 `Strategies/`、模擬與統計 `Simulation/`、事件 `Events/`；細節見 `Engine/CLAUDE.md` |
| `Runner/Program.cs` | 命令列：`--config --games --seed --threads --out --resume --replay --sweep --dump-positions --dump-rate` |
| `Dashboard/` | Blazor Web App（九頁：HOME、模擬、結果、總覽、比較、回放、參數掃描、設定檔、版本控管）；細節見 `Dashboard/CLAUDE.md` |
| `Tests/` | xUnit，只參考 Engine：`SetupTests`、`SettlerMayorTests`、`BuilderCraftsmanTests`、`TraderCaptainTests`、`EndGameScoringTests`、`SimulationTests`（fuzz／重現／續跑／取消）、`StrategyTests`、`ValueModelTests`（推論與 Python 一致、特徵視角、dump 可重現；固定資料在 `Tests/Data/`）、`VersionTests`（黃金樣本：規則或策略的行為變了卻沒進版就失敗；版本清單、`ml/strategy-params.json` 與程式一致；`StrategyRegistry.Resolve`）；情境用 `Tests/Sc.cs`（`Sc.Start` 指定總督與職業） |
| `deploy/runpod/` | RunPod（或任何 Linux）：`setup.sh`（.NET 8、Python 套件、建置、發佈 Runner，可重複執行）、`start.sh`（背景啟動／停止 ML UI 與 Dashboard，只綁 localhost）；說明在 `docs/runpod.md` |
| `ml/` | MCTS 的學習型價值函數（Python 子專案）：ML UI（Streamlit，`ml/start-ui.sh`／`.cmd`，localhost:8501，另外啟動）、訓練（LightGBM、NumPy MLP，背景工作）、產生資料的設定、正式模型 `ml/models/`＋`.meta.json`（使用者的實驗放本機工作區 `ml/local/`，被 git 忽略）、pytest；流程見 `ml/README.md`，細節與契約見 `ml/CLAUDE.md`（資料檔放 `results/ml/`） |
| `tools/tiestats/`、`tools/sparring/` | 分析工具，不在 `PuertoRico.sln`（改 Engine 後要另外 `dotnet build -c Release tools/<名稱>`）；用法寫在各自 `Program.cs` 開頭 |
| `config*.json` | 設定檔範例（Runner 與 Dashboard 共用格式） |
| `PuertoRico.sln`、`Directory.Build.props` | net8.0、Nullable、TreatWarningsAsErrors（csproj 內不要重複設；新程式碼要零警告） |
| `.streamlit/config.toml` | ML UI（Streamlit）的深色主題，與 Dashboard 同色票（Streamlit 從啟動目錄讀，啟動檔都在根目錄執行） |
| `.claude/` | SessionStart hook：雲端 session 自動安裝 .NET 8 並 restore |

## 指令
```bash
dotnet build -c Release
dotnet test -c Release
dotnet run -c Release --project Runner -- --config config.example.json --games 100000 --out results/x.json   # 加 --sweep 跑參數掃描、--resume 續跑、--replay N 看第 N 局
dotnet run -c Release --project Dashboard   # http://localhost:5080，讀 results/
python3 -m pytest ml/tests   # ml/ 的測試（先 pip install -r ml/requirements.txt）
dotnet publish Runner -c Release -o publish/runner   # 發佈 Runner（publish/ 被 git 忽略）；長時間背景工作用 ./publish/runner/Runner，之後建置不會覆寫它
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

## 版本與 hash（改引擎或 ML 前先看；改完要主動提醒使用者並建議版本號）
版本號的清單與每個版本改了什麼在 **`docs/versions.json`**（Dashboard「版本控管」頁、ML UI「版本控管」頁讀同一份；`Tests/VersionTests.cs` 檢查清單最新一筆等於程式裡的數字；每筆的 `commit` 是第一個帶這個版本的 commit，進版的 commit 推送後馬上用下一個 commit 補上）：

| 版本 | 程式裡的位置 | 顯示 | 什麼時候加 |
|---|---|---|---|
| **規則版本** | `EngineInfo.RulesRevision`（規則集 `EngineInfo.RulesVersion` = `base`） | `base-v1`（有變體時 `base-v2-rich-start`） | 遊戲規則（建築、計分、Setup、終局…）或亂數／種子衍生改變，同設定同種子結果不同。所有資料都變舊。 |
| **策略版本**（每個策略一個） | `StrategyRegistry.Revisions` | `harbor-rush-v1` | 該策略的**決策邏輯**改變（含它共用的程式：`HeuristicStrategy`、`TieBreakRules` 改了＝所有手寫策略各加 1；`mcts` 也包含 rollout 呼叫、估值模型推論與特徵集（`FeatureSets`、`FeaturesV1`／`V2`）程式；只「新增」特徵集、舊版模型的對局逐局不變時不用加）。只有用到它的資料變舊。`rule-based` 跟著它的 profile。 |
| **引擎版本**（SemVer） | `EngineInfo.Version` | `0.3.0` | 新增功能、策略、輸出欄位加次版本；不影響結果的修正加修訂版本；規則或策略版本加 1 時至少加次版本。不進 hash。 |
| **特徵版本** | `FeatureSets.LatestVersion` | 整數（最新版；舊版並存） | 要換特徵清單時，**新增一個特徵集**（`FeaturesV{N}.cs`，登錄在 `FeatureSets.All`）並把最新版加 1；**不要改舊版的清單**（模型與資料依它的名稱與順序）。多個版本並存：模型記著訓練時的特徵名稱，引擎依名稱挑對應的特徵集，舊版模型與資料照常可用。 |
| **資料格式版本** | `PositionDump.FormatVersion` | 整數 | `.bin` 紀錄排列改變（只在 `.bin.json` 新增欄位不用加）。 |

**改參數或預設值不用進版本**：引擎把每個座位實際使用的**完整參數**（預設值依人數填好，`StrategyRegistry.Resolve`）連同策略版本記進結果檔與 dump（`resolvedSeats`），hash 用它，所以預設值一改 hash 就不同。新的參數一律透過 `StrategyRegistry.GetDouble`／`GetString` 讀（否則 Resolve 看不到）；延遲到知道人數才讀的策略要實作 `IResolvesParameters`。

**hash**（`ml/fingerprint.py`，ML UI「hash 說明」頁）：資料、模型、對戰各有一個配方 hash，參數全部一樣才會一樣，用來判斷同名檔案差在哪、重複資料、舊版的資料與模型。配方含規則集與規則版本、預留的變體欄位、每個座位的策略版本與完整參數；計入／不計入的參數見該頁與 `ml/CLAUDE.md`。git commit（`EngineInfo.Commit`，結果檔與 dump 的 `engineCommit`）只用來追溯，不進 hash。預測新執行的 hash 用 `ml/strategy-params.json`（引擎產生、測試檢查與程式一致）；沒有 `resolvedSeats` 的舊檔用凍結的 `ml/strategy-params.legacy.json`（**永遠不要重產生它**）。

**黃金樣本**（`Tests/VersionTests.cs`、`Tests/Data/golden.json`）：RULES 案例只有隨機玩家（規則、亂數與 random 策略），其他每個策略各一組案例（它加隨機玩家），只 hash 對局的核心欄位；不含 MCTS（浮點在不同平台可能差一位）。失敗訊息會分開說「規則變了」「X 的預設參數變了（不用進版本）」「X 的決策變了（建議 X 加 1）」。決定好版本後才用 `PR_UPDATE_GOLDEN=1 dotnet test --filter Golden` 重產生 `golden.json` 與 `ml/strategy-params.json`。

**Claude Code 的責任：動到下面這些東西時，主動告訴使用者「這會影響 ○○ 版本／hash」並建議新版本號，經同意後一起改；不要默默改，也不要默默不改。**
1. **改了引擎或策略的程式**：跑 `dotnet test`，照 `GoldenTests` 的訊息判斷：規則變了 → 建議規則版本 +1；某策略的決策變了 → 建議該策略版本 +1；只有預設值變了 → 不進版本，只更新黃金檔。進版時引擎版本至少次版本 +1、`docs/versions.json` 補對應的筆數，並告訴使用者哪些資料與模型變成「舊版」要重產生。只動 MCTS 或估值模型推論時黃金樣本不會失敗，要自己判斷 `mcts` 要不要加 1。
2. **新增策略**：在 `StrategyRegistry.Revisions` 給 1、`docs/versions.json` 的 `strategies` 補一條、更新黃金檔；建議引擎版本次版本 +1。**新增其他功能或輸出欄位**：次版本 +1；只修 bug 且結果不變：修訂版本 +1。
3. **新增特徵集**（不要改舊的）：最新特徵版本 +1、引擎版本次版本 +1；新版的資料要重產生、模型要重訓，舊版的資料與模型不變舊、照常可用（`mcts` 策略版本不用加：版本 1 模型的對局有測試鎖住逐局相同）。**改 `.bin` 排列**：資料格式版本 +1，同步 `positions.py`。
4. **新增訓練參數、會影響結果的設定欄位**：同步 `fingerprint.py`（`LGBM_OPTIONS`／`MLP_OPTIONS`、配方欄位）與「hash 說明」頁；**改 hash 配方的內容（`HASH_FORMAT` 加 1）會讓所有舊 hash 變成「不同」，先問使用者**。
5. 每次改版本號都在 `docs/versions.json` 補一筆（版本、日期、修改內容，最新的在最上面；commit 在推送後補）。
6. commit 後三段回報的「建議」要包含版本建議（若本次有動到上面這些）。

## 使用者的工作習慣
- 回覆用繁體中文；commit 訊息用英文。
- 目前以 4 人局為主：3 人局的議題（調參、模型、實驗）先擱置，記在 `docs/TODO.md`「擱置」，不主動做；使用者指定擱置的待辦也放在那裡。
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
