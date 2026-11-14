# Dashboard（Blazor Web App，Interactive Server）

只參考 Engine；只負責設定／檢視／圖表（「模擬」頁直接呼叫 Engine 的 `BatchSimulator`）。讀到這個資料夾的檔案時自動載入。

## 檔案地圖
**`Components/Pages/`**：Home `/`、Simulate（一般對戰與參數掃描）、Results `/results`、Overview（多檔彙整）、Compare（A/B 並排）、Replay（逐步看盤面）、Sweep、Config。

**`Components/`**
- `BoardView.razor`：回放盤面。精簡版面，連同上下一步要放進一個視窗；中欄寬度＝4 張職業卡（供應區、貨船、交易所）；玩家在兩側，從左下順時針為座位 1→2→3→4。
- `MctsSearch.razor`：MCTS 每個合法動作的 N／Q／SE／ΔQ／Noise／UCT 與佔比、勝率（`Entry.WinRate` 只供顯示）；UCT 最大的動作標 🎯；被選中的動作用紅黃綠燈（`SearchSummary.Assess`，只與第 2 名比，雜訊＝1.5 倍標準誤差 `NoiseZ`）；標題列顯示模擬次數、rollout 策略、回合數、探索係數。**表格下方的說明文字大部分是使用者寫的，改動前先問。** `Entry.Line` 引擎仍保留但畫面不顯示。
- `LegalActions.razor`：沒有 MCTS 搜尋的決策，列出當時所有合法動作並標示選中的（手寫策略有分數時依分數排序）；用決策前的盤面快照重列，不改引擎。
- `GameList.razor`：結果頁的對局列表（`GameFilter` 篩選、排序、分頁，「重播」連到 `replay?file=&game=`）。
- `Layout/MlUiNav.razor`（側欄最後「機器學習」）：一行「🌱 ML UI 執行中●」（綠，新分頁連結）或「ML UI 未啟動○」（紅，按下啟動；啟動中黃◐），每 5 秒檢查 localhost:8501；側欄收合時改成圖示的綠／紅／黃框。啟動：`Services/MlUiLauncher.cs` 先用 `ml/check_env.py` 依啟動檔同樣的順序找套件齊全的 Python（`PR_PYTHON`，Windows `python`→`py`），都沒有就顯示 check_env 的訊息（哪個 Python、要執行的那一行；專案路徑經 `Scrub` 顯示成相對路徑），否則 Windows 用新的 cmd 視窗執行 `ml/start-ui.cmd`、其他系統背景執行 `ml/start-ui.sh`（紀錄 `results/logs/ml-ui.log`），等健康檢查通過。分頁在按下時先開（`App.razor` 的 `prMlTab`，之後才開會被擋成彈出視窗），好了再導向、失敗就關掉。未啟動時下方顯示「新裝置先 python -m pip install -r ml/requirements.txt」。Dashboard 不依賴 ML UI；啟動的 ML UI 獨立於 Dashboard。
- `FilePicker.razor`、`Charts/`（純 SVG：BarChart／StackedBars／LineChart）、`App.razor`（含一小段 JS：回放頁 ←／→ 會點 `#replay-prev`／`#replay-next`；`prMlTab` 給 ML UI 按鈕預先開分頁）、`Layout/`。

**`Services/`**
- `AppState.cs`：載入結果／掃描檔；`ReadConfigAsync` 只讀 config（跳過逐局記錄，大檔很快）；`SetTemplate`（用這份設定再模擬）；畫面上的路徑一律用 `DisplayPath`／`Scrub` 顯示成相對專案根目錄。
- `SimulationService.cs`（背景執行、進度、取消）、`SnapshotEventSink.cs`（回放：每個決策前的狀態、動作、搜尋摘要）。
- `ActionText.cs`（動作的中文說明）、`StrategyInfo.cs`（流派介紹與參數文字；`Groups` 決定頁籤分組）、`Palette.cs`（策略顏色與名稱）、`OverviewPresets.cs`。
- `ValueModelCatalog.cs`：列出 `ml/models/` 的價值模型（讀 `.meta.json` 的人數、種類、對原版 MCTS 最佳勝率；不依賴 Python）；「策略模擬」頁 MCTS 座位參數欄下的「價值模型」下拉選單用它，選擇結果寫回參數文字（`valueModel=ml/models/…`），參數文字仍是唯一的來源。
- `PageMemory.cs`：每個瀏覽器分頁一份的頁面記憶（Results／Sweep 的資料在 `AppState`，本來就保留）。

**`wwwroot/`**：`app.css`（色票 token；只有一套扁平深色主題，沒有淺色模式）、`favicon.svg`。

## 常見修改
- **圖表**：統計放 `Engine/Simulation/ResultAnalysis.cs`（加單元測試），畫圖用 `Components/Charts/`（不引入 JS 套件）；顏色用 CSS 變數（`--series-N`，策略顏色走 `Palette.Color`，顏色跟策略不跟排名）；每張圖附表格檢視；Razor 的 `@for` 裡寫 SVG `<text>` 要包在 `<g>` 裡（`<text>` 是 Razor 保留標籤）。
- **頁面狀態要在切頁後保留**：在該頁的 `Snap` 記錄加欄位（`@implements IDisposable`、`Dispose` 存、`OnInitialized` 還原；範本 `Pages/Overview.razor`）；載入到一半離開不要存半成品（`Memory.Forget`）。
- **策略有增改**：同步 `Services/StrategyInfo.cs`。
- **驗證**：沒有自動化測試；用 Playwright 截圖（切換頁面再回來檢查狀態還在）。

## 注意
- 會把整份結果檔讀進記憶體，並可讀伺服器上任意路徑：只在本機執行（localhost:5080），不要對外開放。
- 一個瀏覽器分頁同時只跑一個模擬任務；大量局數仍建議用 Runner。
- `dotnet run --project Dashboard` 啟動的程序名稱是 `bin/Release/net8.0/Dashboard`（apphost），不是 `Dashboard.dll`：要停掉用 `pkill -f net8.0/Dashboard`；舊的沒停掉時新的會因 5080 被佔用而啟動失敗。
- 「啟動 ML UI」按鈕（`MlUiLauncher`）只執行專案裡固定的啟動檔，不能把任何使用者輸入接進指令列。
