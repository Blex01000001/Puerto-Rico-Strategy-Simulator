# ml/：MCTS 的學習型局面價值函數

把學習得到的模型當作「局面價值函數」，取代 MCTS 第 3 步（rollout）：葉節點不再隨機往下打，而是由模型估計每個座位的回傳值（0.6×勝＋0.4×名次分，與 rollout 版相同的尺度）；選擇、展開、回傳不變，終局葉節點仍用真實分數。
**成效只看對戰勝率**（`mcts/value/`，結果在 `docs/strategy-analysis.md` 第 10 節）；驗證集 MSE 只是訓練有沒有壞掉的檢查。

訓練在 Python（離線），推論在 Engine 內用純 C#（`Engine/Strategies/Mcts/ValueModel.cs`，零 NuGet 相依、可在 RunPod Linux 執行、結果可完全重現）。

## ML UI（訓練與模型清單）
```bash
ml/start-ui.sh          # Windows：雙擊 ml\start-ui.cmd
```
瀏覽器開 `http://localhost:8501`（只有本機連得到）。不需要 Visual Studio，也不需要開 Dashboard。**新裝置第一次使用前，先在專案根目錄執行一次 `python -m pip install -r ml/requirements.txt`**（不要直接打 `pip`：有好幾個 Python 時可能裝到另一個）。啟動檔會挑第一個裝好套件的 Python（Windows 依序試 `python`、`py`；環境變數 `PR_PYTHON` 可指定 python.exe 的完整路徑）；都沒裝好時，`ml/check_env.py` 會印出是哪個 Python 與要執行的那一行（含該 Python 的完整路徑），cmd 視窗會停住讓你看。

也可以從 Dashboard 啟動：左側選單「機器學習」顯示「ML UI 執行中 ●」（綠）或「ML UI 未啟動 ○」（紅；側欄收合時是圖示的綠／紅框）；未啟動時點它，Dashboard 會檢查 Python 與套件，在 Windows 跳出一個 cmd 視窗執行 `ml\start-ui.cmd`（關掉這個視窗就停止 ML UI；已開始的工作不受影響），好了自動在新分頁打開。缺套件時會顯示是哪個 Python 與要執行的那一行指令。
- **訓練**：勾選 `results/ml/` 的資料（依人數分開；正在產生的資料會標「產生中」）、選 LightGBM 或 MLP、填參數（標籤是中文說明＋命令列參數名稱）、取名稱 → 開始訓練。進度條與驗證 loss 曲線每 2 秒更新，結束時顯示驗證成績；同一時間只跑一個工作。
- **模型清單**：`ml/models/` 每個模型的種類、資料、R²、對原版 MCTS 的最佳勝率；點選看參數、資料來源、各回合段誤差、loss 曲線、特徵重要度、所有對戰結果；「並排比較」最多 4 個模型，標出不同的參數。
- 訓練在**獨立的背景程序**執行（`ml/jobs.py`）：關掉瀏覽器、關掉 UI（Ctrl+C）都不會中斷，重開 UI 會接著顯示進度；要停就按「取消這個工作」（不會留下半成品模型）。電腦睡眠或關機造成的中斷會標成「中斷」。工作紀錄在 `results/ml/jobs/<編號>/`（`job.json`、`events.jsonl`、`log.txt`）。
- 資料與結果資料夾跟 Dashboard 相同（`results/`；環境變數 `PR_RESULTS_DIR` 可改，對應 Dashboard 的 `Dashboard:ResultsDirectory`）。
- **資料**：選 `ml/data-configs/` 的設定檔（手寫策略、隨機），或選一個模型做「MCTS＋模型」自我對戰（UI 會把設定檔寫進 `ml/data-configs/<名稱>.json`，可重現），填局數、種子、抽樣率 → 寫到 `results/ml/<名稱>.bin`。
- **對戰驗證**：選模型與對手桌（「對原版 MCTS」：同桌 cheap-engine、build-first（3 人局只有 cheap-engine）；「對手寫策略」：corn-shipper、corn-to-premium、build-first（3 人局 corn-shipper、build-first）），模擬次數、`leafRollout`、局數（24／6 的倍數＝balanced 完全平衡）→ 設定檔寫進 `mcts/value/<名稱>.json`、結果 `results/ml/<名稱>.json`，完成後勝率自動記進模型的 `.meta.json`（`matches`），模型清單與 Dashboard 都看得到。
- **工作**：所有工作的進度、紀錄、取消；側欄隨時顯示目前的工作。
- 資料與對戰工作呼叫**發佈版 Runner**（`publish/runner`，環境變數 `PR_RUNNER_DIR` 可改）；C# 原始碼比發佈版新時會先自動 `dotnet publish`（需要 .NET 8 SDK）。取消時對 Runner 送 Ctrl+C：產生資料保留已完成的局數、對戰寫出部分結果（不記到模型）；**Windows 上是直接結束 Runner，不會保留部分結果**。

在 RunPod 上跑（產生資料、長時間對戰）：見 `docs/runpod.md`。

## 流程

1. **產生資料**：Runner 的 `--dump-positions` 照設定檔打完整局，每個決策點以 `--dump-rate` 的機率抽樣，每個抽到的局面對每個座位各寫一列（特徵從該座位的視角，標籤＝該座位終局的回傳值與勝負）。
   ```bash
   dotnet run -c Release --project Runner -- --config ml/data-configs/4p-hand-a.json --dump-positions results/ml/4p-hand-a.bin --dump-rate 0.01
   ```
   輸出 `<檔>`（固定長度紀錄：float32 reward、float32 win、int32 局號、int16×特徵數）＋ `<檔>.json`（特徵名稱、設定）。結果與執行緒數無關。中途取消（Ctrl+C）時，已完成的局數仍可讀（`.bin.json` 的 `status` 為 `cancelled`）。檔案很大（約 870 bytes／列，2 萬局約 43 萬～60 萬列），放 `results/ml/`（已被 git 忽略）。
2. **訓練**（需要 `python -m pip install -r ml/requirements.txt`）：
   ```bash
   python3 ml/train_lgbm.py --out ml/models/4p-v1.txt "results/ml/4p-*.bin"
   python3 ml/train_mlp.py --out ml/models/4p-mlp-v1.json results/ml
   ```
   資料參數可以是檔案、萬用字元（腳本自己展開，Windows 也能用；加引號避免 shell 先展開）或資料夾（裡面所有 `.bin`）。參數用 `--help` 看。每個模型旁會寫 `<模型>.meta.json`：訓練參數、用了哪些資料（來源、局數、是否為自我對戰與用了哪個模型）、驗證成績、loss 曲線、特徵重要度、套件版本，以及 `matches`（對戰勝率，用 `modelmeta.add_match` 加入）。
   驗證集依「局」切（同一局的局面不會同時出現在訓練與驗證）。`train_mlp.py` 有 PyTorch 就用 PyTorch（`--backend auto`，有 GPU 時 `--device auto` 會用 GPU），沒有就用 NumPy；兩者輸出同一種 JSON，Engine 不分。PyTorch 是選用的（`ml/requirements.txt` 有安裝說明：只要 CPU 版用 PyTorch 的 CPU 下載站，小很多）。兩者都另存 `<模型>.check.txt`（5 列 Python 的預測值＋特徵），可用來確認 C# 推論一致。
3. **使用**：MCTS 參數 `valueModel`（模型路徑；相對路徑先找目前目錄，找不到再往上層找，所以從專案根目錄、`Dashboard/`（VS F5）或 `publish/runner` 執行都能用 `ml/models/x.txt`；Dashboard「策略模擬」頁的 MCTS 座位有下拉選單）、`leafRollout`（展開後先由 `rolloutStrategy` 打幾個決策再估值，預設 0）。設定 `valueModel` 後 `rolloutRounds` 不再使用。
4. **長時間工作**（自我對戰動輒一小時）：先發佈 Runner（`dotnet publish Runner -c Release -o publish/runner`），再用 `./publish/runner/Runner <同樣的參數>` 執行；這段時間內修改、建置程式都不會影響它。改了 Engine 要重新發佈。
5. **迭代**：用「MCTS＋模型」自我對戰產生新資料（`ml/data-configs/4p-selfplay-*.json`），和舊資料一起重訓，再對戰比較。

## 檔案
| 檔案 | 用途 |
|---|---|
| `positions.py` | 讀 dump（檢查格式、版本、檔案大小；展開萬用字元與資料夾）、依局切驗證集 |
| `ui.py`、`start-ui.sh`／`start-ui.cmd` | ML UI（Streamlit）與啟動檔 |
| `jobs.py`、`job_runner.py` | 背景工作（獨立程序、心跳、取消、紀錄） |
| `modelmeta.py` | `<模型>.meta.json` 的寫入／讀取、把對戰結果記到模型 |
| `tests/` | pytest（`python3 -m pytest ml/tests`，不需要 .NET） |
| `requirements.txt` | Python 套件 |
| `train_lgbm.py` | LightGBM（`cross_entropy` 目標，標籤 0～1） |
| `train_mlp.py` | MLP（ReLU 隱藏層＋sigmoid 輸出，Adam，L2，學習率每 4 個 epoch 減半，提早停止）；PyTorch 或 NumPy，匯出同一種 JSON |
| `data-configs/` | 產生資料用的設定檔（手寫策略混桌、隨機、MCTS 自我對戰） |
| `models/` | 訓練好的模型（LightGBM 文字檔約 3 MB、MLP JSON 約 3 MB） |

## 注意
- 特徵清單在 `Engine/Strategies/Mcts/ValueFeatures.cs`（全部是小整數；玩家區塊依「自己、下家…」排列，3 人局第 4 區塊全 0）。**改了特徵清單，舊模型會拒絕載入**（載入時逐一比對特徵名稱），要重新產生資料並重訓。
- C# 只支援 LightGBM 的數值切分（不支援類別特徵）與單一輸出；MLP 只支援 ReLU。MLP 推論每個輸出依輸入順序累加，結果不受 CPU 的 SIMD 寬度影響。
- 模型依人數分開訓練與使用（`4p-*` 只給 4 人局）。
- 推論成本：LightGBM 400 棵樹約 20 µs、MLP 256-128 約 30 µs（每個座位一次；一次 8 回合隨機 rollout 約 130 µs）。
