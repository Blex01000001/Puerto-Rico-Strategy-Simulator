# ml/：MCTS 的學習型局面價值函數

把學習得到的模型當作「局面價值函數」，取代 MCTS 第 3 步（rollout）：葉節點不再隨機往下打，而是由模型估計每個座位的回傳值（0.6×勝＋0.4×名次分，與 rollout 版相同的尺度）；選擇、展開、回傳不變，終局葉節點仍用真實分數。
**成效只看對戰勝率**（`mcts/value/`，結果在 `docs/strategy-analysis.md` 第 10 節）；驗證集 MSE 只是訓練有沒有壞掉的檢查。

訓練在 Python（離線），推論在 Engine 內用純 C#（`Engine/Strategies/Mcts/ValueModel.cs`，零 NuGet 相依、可在 RunPod Linux 執行、結果可完全重現）。

## 流程

1. **產生資料**：Runner 的 `--dump-positions` 照設定檔打完整局，每個決策點以 `--dump-rate` 的機率抽樣，每個抽到的局面對每個座位各寫一列（特徵從該座位的視角，標籤＝該座位終局的回傳值與勝負）。
   ```bash
   dotnet run -c Release --project Runner -- --config ml/data-configs/4p-hand-a.json --dump-positions results/ml/4p-hand-a.bin --dump-rate 0.01
   ```
   輸出 `<檔>`（固定長度紀錄：float32 reward、float32 win、int32 局號、int16×特徵數）＋ `<檔>.json`（特徵名稱、設定）。結果與執行緒數無關。中途取消（Ctrl+C）時，已完成的局數仍可讀（`.bin.json` 的 `status` 為 `cancelled`）。檔案很大（約 870 bytes／列，2 萬局約 43 萬～60 萬列），放 `results/ml/`（已被 git 忽略）。
2. **訓練**（需要 `pip install lightgbm numpy`）：
   ```bash
   python3 ml/train_lgbm.py --out ml/models/4p-v1.txt results/ml/4p-*.bin
   python3 ml/train_mlp.py --out ml/models/4p-mlp-v1.json results/ml/4p-*.bin
   ```
   驗證集依「局」切（同一局的局面不會同時出現在訓練與驗證）。`train_mlp.py` 只用 NumPy（PyTorch 的下載站被網路擋住）。兩者都另存 `<模型>.check.txt`（5 列 Python 的預測值＋特徵），可用來確認 C# 推論一致。
3. **使用**：MCTS 參數 `valueModel`（模型路徑，相對於執行目錄）、`leafRollout`（展開後先由 `rolloutStrategy` 打幾個決策再估值，預設 0）。設定 `valueModel` 後 `rolloutRounds` 不再使用。
4. **迭代**：用「MCTS＋模型」自我對戰產生新資料（`ml/data-configs/4p-selfplay-*.json`），和舊資料一起重訓，再對戰比較。

## 檔案
| 檔案 | 用途 |
|---|---|
| `positions.py` | 讀 dump（檢查格式與檔案大小）、依局切驗證集 |
| `train_lgbm.py` | LightGBM（`cross_entropy` 目標，標籤 0～1） |
| `train_mlp.py` | MLP（ReLU 隱藏層＋sigmoid 輸出，Adam），匯出 JSON |
| `data-configs/` | 產生資料用的設定檔（手寫策略混桌、隨機、MCTS 自我對戰） |
| `models/` | 訓練好的模型（LightGBM 文字檔約 3 MB、MLP JSON 約 3 MB） |

## 注意
- 特徵清單在 `Engine/Strategies/Mcts/ValueFeatures.cs`（全部是小整數；玩家區塊依「自己、下家…」排列，3 人局第 4 區塊全 0）。**改了特徵清單，舊模型會拒絕載入**（載入時逐一比對特徵名稱），要重新產生資料並重訓。
- C# 只支援 LightGBM 的數值切分（不支援類別特徵）與單一輸出；MLP 只支援 ReLU。MLP 推論每個輸出依輸入順序累加，結果不受 CPU 的 SIMD 寬度影響。
- 模型依人數分開訓練與使用（`4p-*` 只給 4 人局）。
- 推論成本：LightGBM 400 棵樹約 20 µs、MLP 256-128 約 30 µs（每個座位一次；一次 8 回合隨機 rollout 約 130 µs）。
