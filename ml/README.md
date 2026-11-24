# ml/：MCTS 的學習型局面價值函數

把學習得到的模型當作「局面價值函數」，取代 MCTS 第 3 步（rollout）：葉節點不再隨機往下打，而是由模型估計每個座位的回傳值（0.6×勝＋0.4×名次分，與 rollout 版相同的尺度）；選擇、展開、回傳不變，終局葉節點仍用真實分數。
**成效只看對戰勝率**（`mcts/value/`，結果在 `docs/strategy-analysis.md` 第 10 節）；驗證集 MSE 只是訓練有沒有壞掉的檢查。

訓練在 Python（離線），推論在 Engine 內用純 C#（`Engine/Strategies/Mcts/ValueModel.cs`，零 NuGet 相依、可在 RunPod Linux 執行、結果可完全重現）。

## ML UI（訓練與模型）
```bash
ml/start-ui.sh          # Windows：雙擊 ml\start-ui.cmd
```
瀏覽器開 `http://localhost:8501`（只有本機連得到；深色主題與 Dashboard 相同，設定在根目錄 `.streamlit/config.toml`）。不需要 Visual Studio，也不需要開 Dashboard。**新裝置第一次使用前，先在專案根目錄執行一次 `python -m pip install -r ml/requirements.txt`**（不要直接打 `pip`：有好幾個 Python 時可能裝到另一個）。啟動檔會挑第一個裝好套件的 Python（Windows 依序試 `python`、`py`；環境變數 `PR_PYTHON` 可指定 python.exe 的完整路徑）；都沒裝好時，`ml/check_env.py` 會印出是哪個 Python 與要執行的那一行（含該 Python 的完整路徑），cmd 視窗會停住讓你看。

也可以從 Dashboard 啟動：左側選單「機器學習」顯示「ML UI 執行中 ●」（綠）或「ML UI 未啟動 ○」（紅；側欄收合時是圖示的綠／紅框）；未啟動時點它，Dashboard 會檢查 Python 與套件，在 Windows 跳出一個 cmd 視窗執行 `ml\start-ui.cmd`（關掉這個視窗就停止 ML UI；已開始的工作不受影響），好了自動在新分頁打開。缺套件時會顯示是哪個 Python 與要執行的那一行指令。
- **模型訓練/蒸餾**：勾選 `results/ml/` 的資料（依人數分開；正在產生的資料會標「產生中」）、選 LightGBM 或 MLP、填參數（標籤是中文說明＋命令列參數名稱）、取名稱 → 開始訓練。進度條與驗證 loss 曲線每 2 秒更新，結束時顯示驗證成績；同一時間只跑一個工作。
- **訓練資料**（管理）：`results/ml/` 的每份資料一列（人數、局數、列數、抽樣率、特徵版本、大小、策略、hash、規則版本）；上方快篩（人數、特徵版本、規則版本，各一個框）。勾一列看詳細資料（座位與參數、用它訓練過的模型、版本是否過舊）；「重新命名」「刪除」只在這裡（資料與 `.json` 一起；hash 不變，本機模型的紀錄跟著改名）；勾選一到多列可「複製詳細資訊」（精簡文字、有字數提示、不含路徑）。
- **估值模型**（管理）：正式（`ml/models/`）與本機（`ml/local/models/`）每個模型一列：種類、人數、特徵版本、資料、R²、對戰勝率、規則版本；上方快篩（位置、種類、人數、規則版本，各一個框）。勾一個模型在下方看詳細資料（對戰結果、訓練資料、參數、各回合段誤差、loss 曲線、特徵重要度），勾 2～4 個並排比較；「重新命名」「設為正式模型」「移到本機」「刪除」只在這裡；勾選的模型可「複製詳細資訊」（精簡文字、有字數提示、不含路徑）。
- 訓練在**獨立的背景程序**執行（`ml/jobs.py`）：關掉瀏覽器、關掉 UI（Ctrl+C）都不會中斷，重開 UI 會接著顯示進度；要停就按「取消這個工作」（不會留下半成品模型）。電腦睡眠或關機造成的中斷會標成「中斷」；程序還在但超過 30 秒沒有回報時標成「失聯」，排隊的工作會先暫停等它，確定卡住了可以「強制結束」。工作紀錄在 `results/ml/jobs/<編號>/`（`job.json`、`events.jsonl`、`log.txt`）。
- 資料與結果資料夾跟 Dashboard 相同（`results/`；環境變數 `PR_RESULTS_DIR` 可改，對應 Dashboard 的 `Dashboard:ResultsDirectory`）。
- **模擬對局採樣**：設定檔決定「哪幾個策略互打」（人數、每個座位的策略與參數、局數、種子；座位順序每局隨機）。三種來源（「1. 採樣來源模型」）：從下拉選單選 `ml/data-configs/` 的設定檔（全部設定檔的列表與刪除在下方「管理設定檔」裡）；**自訂組合**（每個座位自己選策略，MCTS 座位可選模擬次數、估值模型、leafRollout，其他座位可填參數；存成 `ml/data-configs/<名稱>.json`，不會覆蓋同名的既有設定）；或選一個模型做「MCTS＋模型」自我對戰（UI 會把設定檔寫進 `ml/data-configs/<名稱>.json`，可重現），填局數、種子、抽樣率 → 寫到 `results/ml/<名稱>.bin`。
- **對戰驗證**：選模型與對手桌（「對另一個估值模型」：同桌兩個 MCTS 各用一個模型，加 cheap-engine、build-first（3 人局只有 cheap-engine），預設 480 局、兩邊各 300 次，結果記在上面選的模型；「對原版 MCTS」：同桌 cheap-engine、build-first（3 人局只有 cheap-engine）；「對手寫策略」：corn-shipper、corn-to-premium、build-first（3 人局 corn-shipper、build-first）），模擬次數、`leafRollout`、局數（24／6 的倍數＝balanced 完全平衡）→ 設定檔寫進 `mcts/value/<名稱>.json`、結果 `results/ml/<名稱>.json`，完成後勝率自動記進模型的 `.meta.json`（`matches`），模型清單與 Dashboard 都看得到。
- **流程排定**（排程）：把「產生資料 → 訓練 → 多場對戰」排成一條，一次加入排隊。三段都可以有任意個項目（0 個也行）：按「新增」會跳出設定視窗（背景變暗），設定完回到頁面，只顯示這個項目的詳細資訊（唯讀，要改就移除後重新新增）。資料可以有好幾份；每個模型自己選用哪些資料（這條排程的資料和既有資料）；每場對戰自己選被測模型（這條排程的模型或既有模型），「填入標準驗證組」替每個模型各加四場。工作的順序：所有資料先跑，再每個模型接著跑它自己的對戰。任何一個工作失敗、被取消或中斷，這條排程還沒開始的工作會全部取消（已經產生的檔案保留）；設定可存成範本（`ml/local/pipelines/`，舊版的範本會自動轉換）。關掉 UI 排程照樣跑完。
- **排程佇列**：工作列表（名稱、狀態、經過時間、進度、取消／取消佇列、備註；失敗的錯誤訊息在備註裡，預設收折），下方「工作詳細」看紀錄與 loss 曲線（每個工作一張小卡，左邊框顏色表示狀態）；左側導覽最下方顯示正在跑的工作，其他排隊的只用小字寫還剩幾項。
- **排隊**：已有工作在跑時，各頁的開始鈕會變成「加入排隊」（可以開始時是藍色，不能開始時鎖住並在右邊用紅字寫原因），新工作依加入的順序一個接一個執行（一次一個：每個工作都會用滿 CPU，同時跑不會比較快）。關掉 ML UI 也會繼續；前一個失敗或取消，下一個照樣開始。「排程佇列」頁列出執行中與排隊中的工作，排隊中的可以「移出佇列」。兩個工作不能寫同一個輸出檔（排隊中的也算）。
- 資料與對戰工作呼叫**發佈版 Runner**（`publish/runner`，環境變數 `PR_RUNNER_DIR` 可改）；C# 原始碼比發佈版新時會先自動 `dotnet publish`（需要 .NET 8 SDK）。取消時對 Runner 送 Ctrl+C：產生資料保留已完成的局數、對戰寫出部分結果（不記到模型）；**Windows 上是直接結束 Runner，不會保留部分結果**。

在 RunPod 上跑（產生資料、長時間對戰）：見 `docs/runpod.md`。

## 本機工作區與正式模型
- ML UI 產生的東西都放在本機工作區 **`ml/local/`**（被 git 忽略，不會出現在 Visual Studio 的 Git 變更裡）：訓練的模型 `ml/local/models/`、自訂組合與自我對戰設定 `ml/local/data-configs/`、對戰設定 `ml/local/matches/`，以及正式模型在這台電腦跑的對戰紀錄 `ml/local/match-records/`。
- **正式模型**在 `ml/models/`（進 git），總表與狀態在 `docs/models.md`。ML UI 與 Dashboard 會同時列出兩邊的模型並標「正式／本機」。
- 本機模型取錯名字：「估值模型」→ 勾選 →「重新命名」（模型、`.meta.json`、`.check.txt` 一起改，hash 不變；正式模型不能在這裡改名）。
- 本機模型驗證後要保留：「估值模型」→ 勾選 →「設為正式模型」（三個檔一起搬到 `ml/models/`），再 commit，並在 `docs/models.md` 補一列（`python3 ml/model_report.py` 會印出數字）。
- 以前直接存在 `ml/models/`、git 沒追蹤的模型：「估值模型」→ 勾選 →「移到本機」。

## 配方 hash （同名檔案、重複資料、舊資料）
每份資料、每個模型、每場對戰都有一個**配方 hash**（SHA-256，畫面顯示前 8 碼）：把決定結果的參數整理成固定格式再算 hash，參數全都一樣 hash 才會一樣。引擎對設定與種子是確定的，所以**hash 相同＝重跑只會得到同一份內容**。
- 同名檔案：配方相同→提示「完全相同，不需要覆寫」；不同→列出差異（例如「局數 20,000 → 200,000、抽樣率 0.01 → 0.001」）；被哪些模型用過也會列出。
- 不同名但配方相同：提示重複；訓練時勾到配方相同的資料也會警告。
- 排隊中或執行中的工作要讀的檔案（訓練資料、對戰用的模型）不能被覆寫。
- 計入配方：規則集與規則版本、人數、局數、種子、抽樣率、座位順序、每個座位的策略、**策略版本**與**完整參數**（設定檔沒寫的參數用預設值補上，所以改預設值 hash 也會變）、估值模型的**檔案內容**（不是檔名）、特徵版本、訓練參數。不計：檔名、執行緒數、座位 id、引擎版本與 git commit、套件版本。
- **規則版本**（`base-v1`，`EngineInfo.RulesRevision`）只管遊戲規則與亂數；**策略版本**（`harbor-rush-v1`）是每個策略自己的決策邏輯版本。兩者都由人手動遞增，引擎的黃金樣本測試會在忘記加時失敗，並分辨「預設值改了（不用進版）」與「邏輯改了」。比目前舊的資料與模型，「版本狀態」會寫「舊：…」，建議重新產生。各種版本號與每個版本的修改在「版本控管」頁（`docs/versions.json`），完整的 hash 說明在 ML UI 的「hash 說明」頁。
- 舊資料（`.bin.json`）與舊對戰結果直接現算 hash；早期補寫的舊模型沒有 hash，標「舊紀錄」。對戰紀錄另存模型檔案的 hash，模型之後被覆寫時，舊結果會標「模型檔已更新」。

## 流程

1. **產生資料**：Runner 的 `--dump-positions` 照設定檔打完整局，每個決策點以 `--dump-rate`（沒給就用設定檔的 `output.dumpRate`，再沒有就 0.02）的機率抽樣，每個抽到的局面對每個座位各寫一列（特徵從該座位的視角，標籤＝該座位終局的回傳值與勝負）。
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
- 特徵集在 `Engine/Strategies/Mcts/`：`FeaturesV1.cs`（430 個，凍結）、`FeaturesV2.cs`（512 個＝版本 1 原樣＋82 個衍生特徵）（全部是小整數；玩家區塊依「自己、下家…」排列，3 人局第 4 區塊全 0）。**多個版本並存**：模型記著訓練時的特徵名稱，引擎依名稱挑對應的版本，所以舊模型與舊資料照常可用；新資料預設用最新版（「模擬對局採樣」的「特徵版本」，或 Runner `--feature-version`），一次訓練只能用同一版的資料，訓練出的模型屬於那一版。
- C# 只支援 LightGBM 的數值切分（不支援類別特徵）與單一輸出；MLP 只支援 ReLU。MLP 推論每個輸出依輸入順序累加，結果不受 CPU 的 SIMD 寬度影響。
- 模型依人數分開訓練與使用（`4p-*` 只給 4 人局）。
- 推論成本：LightGBM 400 棵樹約 20 µs、MLP 256-128 約 30 µs（每個座位一次；一次 8 回合隨機 rollout 約 130 µs）。
