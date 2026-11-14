# ml/（學習型局面價值函數：訓練端）

Python 子專案：產生資料用 Runner（C#），訓練在這裡，推論在 Engine（C#）。讀到這個資料夾的檔案時自動載入；全專案規則在根目錄 `CLAUDE.md`，流程與指令在 `ml/README.md`。

## 檔案地圖
- `positions.py`：讀 Runner 的 dump（`.bin`＋`.bin.json`）；`expand`（萬用字元／資料夾展開）、`read_meta`（格式、版本檢查）、`load`（多檔需同特徵清單、`featureVersion`、人數）、`split`（依局切驗證集）。
- `modelmeta.py`：`<模型>.meta.json`（參數、資料來源、驗證成績、特徵重要度、環境、`matches` 對戰勝率）；`write`／`read`／`match_entry`／`add_match`。
- `train_lgbm.py`、`train_mlp.py`：`train(data, out, progress=None, log=print, **options)` 可匯入（ML UI 用），命令列只是包一層；都寫 `<模型>`、`.meta.json`、`.check.txt`。
- `ui.py`：ML UI（Streamlit，`streamlit run ml/ui.py`；頁籤「訓練」「模型清單」）。啟動檔 `start-ui.sh`／`start-ui.cmd`（綁 localhost:8501、隱藏 Deploy 鈕）。路徑一律顯示成相對專案根目錄（`rel`／`scrub`，與 Dashboard 相同規則）。
- 工作種類（`job_runner.py`）：`train_lgbm`／`train_mlp`（取消＝結束程序）、`dump`、`match`（呼叫發佈版 Runner `dotnet publish/runner/Runner.dll`，`PR_RUNNER_DIR` 可改；原始碼較新會先自動發佈；從輸出解析 `n/total games` 當進度；取消送 SIGINT，Windows 直接結束；`match` 完成後 `modelmeta.add_match`）。UI 寫的設定檔：自我對戰 `ml/data-configs/<名稱>.json`、對戰 `mcts/value/<名稱>.json`。
- `jobs.py`：背景工作（`results/ml/jobs/<id>/`：`job.json` 狀態與心跳、`events.jsonl` 進度、`log.txt`、`cancel` 旗標檔）；`start`／`cancel`／`list_jobs`／`active_job`／`events`／`wait`；同時只允許一個工作。`job_runner.py`：在獨立程序執行一個工作（POSIX `start_new_session`、Windows `CREATE_NEW_PROCESS_GROUP|DETACHED_PROCESS`），心跳執行緒看到 `cancel` 就結束程序。
- `data-configs/`：產生資料的 Runner 設定檔（手寫混桌、隨機、`4p-selfplay-*`＝MCTS＋模型自我對戰）。
- `models/`：模型＋`.meta.json`＋`.check.txt`（進 git）。早期模型的 `.meta.json` 是補寫的（`params.note`、`training.note` 會註明）。
- `tests/`：pytest（`conftest.py` 產生假 dump）：`python3 -m pytest ml/tests`。`test_runner_jobs.py` 需要 .NET SDK（沒有就略過），會把 Runner 發佈到暫存資料夾。
- `requirements.txt`：`pip install -r ml/requirements.txt`。
- `make_test_fixture.py`：重產 C# 測試用的小模型 `Tests/Data/tiny-lgbm.*`（改特徵後要跑）。

## 契約（兩邊要一起改）
| 契約 | 定義在 | 讀的人 |
|---|---|---|
| 特徵清單（名稱、順序、`featureVersion`） | `Engine/Strategies/Mcts/ValueFeatures.cs` | dump、`positions.py`、模型（訓練時寫入特徵名稱）、C# 推論（載入時逐一比對） |
| dump 格式（`formatVersion`、紀錄排列） | `Engine/Simulation/PositionDump.cs` | `positions.py`（`FORMAT_VERSION`、`record_dtype`） |
| 模型格式（LightGBM 文字檔、MLP JSON） | 訓練腳本寫出 | `Engine/Strategies/Mcts/ValueModel.cs` |

## 常見修改
- **改特徵**：改 `ValueFeatures.cs`（遞增 `Version`）→ 重新產生所有資料 → 重訓；舊模型在 Engine 會被拒（刻意）。`Tests/Data/tiny-lgbm.*` 也要用新資料重產：`python3 ml/make_test_fixture.py results/ml/<任一新 dump>.bin`。
- **改 dump 格式**：C# 遞增 `PositionDump.FormatVersion`，同步 `positions.FORMAT_VERSION` 與 `record_dtype`，兩邊測試一起跑。
- **加訓練參數**：加進 `DEFAULTS`、`train()` 的 `params`（會寫進 `.meta.json`）與 argparse；測試在 `tests/test_train.py`。
- **新模型種類**：Engine 要先能推論（`ValueModel.cs` 加類別＋與 Python 一致的測試），再寫訓練腳本；輸出格式不變的改寫（例如 MLP 改 PyTorch）只要 `.check.txt` 與 C# 比對一致。
- **ML UI 加頁籤或工作種類**：工作種類加進 `jobs.KINDS` 與 `job_runner.run`（產生資料、對戰要呼叫發佈版 Runner：`publish/runner/Runner`，進度從 Runner 輸出解析）；頁面加在 `ui.py` 的 `main()`；需要即時更新的區塊用 `@st.fragment(run_every=...)`，工作狀態改變時整頁 `st.rerun(scope="app")`（`job_panel` 的做法）。測試：`tests/test_jobs.py`（真的開程序）、`tests/test_ui.py`（`AppTest` 無頭執行）；畫面用 Playwright 截圖確認（Streamlit 的表格是 canvas，勾選列要點座標）。
- **對戰結果記到模型**：`modelmeta.add_match(<模型>, <Runner 結果檔>)`（同一結果檔重覆加只會取代）。

## 雷
- 訓練資料很大（約 870 bytes／列）：LightGBM 會轉成 float32（257 萬列約 4.4 GB），MLP 保持 int16 逐批標準化；不要在 MLP 先整份轉 float（第一次就因記憶體不足被系統停掉）。
- 驗證集 MSE／R² 和勝率對不上（資料分布換了 R² 就會變），判斷模型只看對戰勝率（`matches`）。
- 長時間產生資料用發佈版 Runner（`./publish/runner/Runner`），見 `ml/README.md`。
- Streamlit 的下拉選單不會更新已顯示選項的文字：選項標籤不要放會變的狀態（`job_panel` 把狀態放在旁邊）。表格裡數值欄的缺值會顯示灰色 None：要顯示「—」就先轉成文字（`models_table`）。
- 用 UI 測試資料／對戰時若有別的 Runner 背景工作正在用 `publish/runner`，啟動 UI 前設 `PR_RUNNER_DIR=<暫存資料夾>`：自動重新發佈會覆寫執行中的 dll。測完要把 `ml/models/*.meta.json` 多出的 `matches` 還原、刪掉 UI 寫的 `mcts/value/`、`ml/data-configs/` 測試設定檔。
- 背景工作的程序不跟著 UI 結束：測試或手動實驗後記得看 `results/ml/jobs/` 有沒有還在跑的；`ml/models/` 裡測試用的模型要刪掉再 commit。
- 這個雲端環境擋住 PyTorch 的 CPU 版下載站；PyPI 的 `torch` 一定要帶 CUDA 函式庫（不帶就 import 失敗），完整安裝約 8 GB。使用者電腦裝 CPU 版即可。
- `train_mlp.py` 兩個後端（`fit_torch`／`fit_numpy`）要維持同樣的訓練規則（He 初始化、Adam＋L2、每 4 epoch 學習率減半、提早停止取最好的一輪）；匯出一律走同一段 JSON，`tests/test_train.py` 兩個後端都測（沒有 torch 就略過）並用 NumPy 從 JSON 重算 check 列。
