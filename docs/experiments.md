# 實驗設定索引

各資料夾的設定檔做了什麼、怎麼重跑。結論都在 `docs/strategy-analysis.md`（括號內是節次）；輸出一律寫到 git 忽略的 `results/`。

## 根目錄範例設定
`config.example.json`（3 人）、`config.4p.example.json`、`config.sweep.example.json`（參數掃描）、`config.corn-vs-random.json`（corn-shipper 對兩個隨機玩家）、`config.strategies-compare.json`（三個手寫原型互打）。

## `tournaments/`：手寫策略對戰（第 1、2、7 節）
`balanced` 座位，4 人 100,008 局／3 人 100,002 局（`*monopoly-effect*` 為 10,008／10,002 局）。`tournaments/run.sh [局數]` 全部重跑。

## `sweeps/`：參數掃描（Runner 加 `--sweep`）
| 資料夾 | 內容 | 節次 |
|---|---|---|
| `sweeps/*.json` | 4 人局第一輪（corn／premium／harbor／build），`rotate` | 4 |
| `round2/`、`round3/` | 4 人局第二、三輪，`rotate` | 4 |
| `3p/`、`3p-round3/` | 3 人局，每個目標對三種對手組合，`rotate` | 4 |
| `round4/` | cheap-engine（`buildThreshold`／`tileCap`／`smallValue`） | 4、5.1 |
| `round5/` | 座位 `random` 重掃（最佳值對座位排列穩健） | 4 |
| `round6/` | wharf-rush，`balanced` | 7.1 |
| `round7/` | wharf-premium | 7.5 |
| `round8/` | `randomTies` 同分對照實驗 | 8.1 |
| `round9/` | 開拓者同分順序 2×2（含 `tieTile` 文字參數） | 8.3 |
| `round10/` | corn-shipper／cheap-engine／premium 的同分順序 2×2（無效果） | 8.4 |
| `round11/` | cheap-engine 建築／出貨同分、corn／premium 選職業同分（引擎順序已最好） | 8.5 |
| `round12/`、`round12c/` | build-first 3 人局 `quarryTarget` 掃描與確認（最佳值取決於對手，不改預設） | 8.6 |
| `round13/` | cheap-engine 的 `roleCoinWeight`（預設未改） | 9 |

`round10/` 之後各有 `run.sh`。第一到第三輪用 `rotate`，絕對勝率帶排列偏差（第 0 節），只看相對趨勢。

## `mcts/`：MCTS 實驗（第 5、7.2 節）
- `*-vs-hand.json`：不同模擬次數／rollout 對手寫策略；`4p-mcts-behavior.json`、`4p-mcts-selfplay.json`：行為分析與自我對戰（5.1）。
- `ab-*.json`：同桌兩個 MCTS 的 A/B 比較（rollout 長度、模擬次數）；未用新同分預設重跑。
- `*wharf*.json`、`4p-mcts-vs-corn-harbor-cheap.json`：MCTS 當 wharf-rush 的陪練（7.2）。
- `value/`：MCTS＋學習型價值函數（`valueModel`）對原版 MCTS（同桌 cheap-engine、build-first，balanced 240 局）與對手寫策略（`4p-v2-vs-hand`，同第 5 節那桌）（第 10 節）；模型與產生資料的設定在 `ml/`（見 `ml/README.md`）。
- `sparring/`：MCTS 對 cheap-engine，用 `tools/sparring` 產生打法報表（第 9 節）；`mcts/sparring/run.sh` 重跑，報表在 `results/sparring/*.md`。
- 全部 `balanced`；MCTS 慢（4 人局 480 局約 100 秒，4 核心），每桌只有數百局，勝率誤差約 ±4～7 個百分點。

## `tools/`：分析工具（不在 `PuertoRico.sln`）
- `tiestats`：手寫策略決策的同分比例與最常見的同分組合（第 8 節）。`dotnet run -c Release --project tools/tiestats -- 960 777 [策略,策略]`
- `sparring`：打一份設定檔的桌子，依策略列出打法（選職業、每回合的金幣／分數／建築／殖民者、生產／出貨／賣貨／爛貨、建築取得率）。`dotnet run -c Release --project tools/sparring -- <設定檔> [局數]`
- 改了 Engine 之後要重新 build 工具，否則會用到舊的 Engine。
