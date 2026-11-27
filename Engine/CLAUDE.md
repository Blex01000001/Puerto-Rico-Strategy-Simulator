# Engine（規則引擎、策略、模擬）

零 UI／Windows 相依。讀到這個資料夾的檔案時自動載入；全專案規則在根目錄 `CLAUDE.md`。

## 檔案地圖
**`Game/`**
- `GameState.cs`：可複製狀態（只有數值與固定長度陣列）。`GameAction.cs`：`ActionType` 與動作。
- `Rules.cs`：`GetLegalActions`／`Apply`／推進；`Rules.<階段>.cs`（Settler／Mayor／Builder／Craftsman／Trader／Captain）各有 `Fill*`（列合法動作）與 `Apply*`。
- `Setup.cs`、`Scoring.cs`、`Invariants.cs`、`Rng.cs`；靜態表：`Buildings.cs`、`GameConstants.cs`。
- `EngineInfo.cs`：引擎版本 `Version`、規則集與規則版本 `RulesVersion`／`RulesRevision`、`Commit`（版本規則在根目錄 `CLAUDE.md`「版本與 hash」）。

**`Strategies/`**
- `IStrategy.cs`（唯一介面）、`RandomStrategy.cs`、`GuidedRandomStrategy.cs`（MCTS rollout 用的帶偏好隨機）、`StrategyRegistry.cs`（名稱→工廠；手寫策略只登錄在 `HandWritten`，同時是 `rule-based` 的 profile，`HandWrittenNames` 列出；`GetDouble`／`GetString` 讀 `params`；`Revisions` 各策略的邏輯版本；`Resolve` 解析出座位實際使用的完整參數與策略版本，靠 `ParamRecorder.cs` 記錄讀到的值，延遲讀參數的策略實作 `IResolvesParameters`）。
- 註冊名稱：`random`、`guided-random`、`mcts`、`corn-shipper`、`corn-to-premium`、`harbor-rush`、`build-first`、`cheap-engine`、`wharf-rush`、`wharf-premium`、`corn-monopoly`、`corn-monopoly-tiles`、`corn-monopoly-hoard`，或 `rule-based`＋`params.profile`。
- `RuleBased/HeuristicStrategy.cs`：手寫策略的共用打分基底（每個選擇打分取最高，子類別覆寫掛鉤：`TileValue`、`BuildingWanted`、`SlotValue`、各 `*RoleValue`、`RoleCoinWeight`…）。
- `RuleBased/` 子類別：`CornShipper`（玉米出貨）、`CornToPremium`（前期玉米、中後期菸草／咖啡）、`HarborRush`（先港口，後期加 Wharf）、`BuildFirst`（採石場折扣、依終局加成挑大型建築）、`CheapEngine`（便宜 1 分建築、少種植園、頻繁出貨；實驗參數 `roleCoinWeight` 預設 1）、`WharfRush`、`WharfPremium`、`CornMonopoly`（搗亂；`grab`／`hoard` 旗標分出 `-tiles`、`-hoard` 變體）。
- `RuleBased/TieBreakRules.cs`：同分的第二準則（字典式，只在主要分數完全相同時生效）。文字參數 `tieTile`／`tieGood`／`tieRole`／`tieBuild`，`tieOpponent` 預留。預設＝引擎順序；只有 build-first／harbor-rush／wharf-rush 有 `DefaultTieTile`＝`hacienda>corn>sugar>indigo>tobacco>coffee>quarry`（`tieTile: ""` 關閉）。策略的偏好寫在自己的規則裡，基底不內建「常理」。
- 實驗參數 `randomTies`（預設 0；1＝開拓者＋工匠額外貨物、2＝市長以外所有階段、3＝只有開拓者、4＝只有工匠額外貨物，同分時隨機）。
- `Mcts/MctsStrategy.cs`：UCT，`params.simulations`／`rolloutStrategy`／`rolloutRounds`／`exploration`／`valueModel`（葉節點改用模型估值）／`leafRollout`（有模型且 4 人局預設 `MctsStrategy.DefaultLeafRollout`＝40，其他情況 0；實作是 `IResolvesParameters`，要知道人數才讀；改預設要同步 `ml/fingerprint.py` 的 `DEFAULT_LEAF_ROLLOUT`，測試會比對）。
- `Mcts/FeatureSets.cs`（`FeatureSet` 抽象類別＋`FeatureSets` 登錄：`All`、`Latest`、`Get(版本)`、`Find(名稱)`；`LatestVersion` 常數給 `ml/fingerprint.py` 讀）、`Mcts/FeaturesV1.cs`（版本 1，430 個特徵，**凍結**）、`Mcts/FeaturesV2.cs`（版本 2 ＝ 版本 1 原樣＋82 個衍生特徵：各職業被誰選走、每個座位能出貨／能賣／能蓋／能生產多少…）；局面特徵都從某座位視角、全部小整數。`Mcts/ValueModel.cs`（`IValueModel`：LightGBM 文字模型與 MLP JSON 的純 C# 推論，依路徑快取；`ValueModels.Resolve`：相對路徑找不到時往目前目錄與程式目錄的上層找）。
- 選用介面（都在 `IDecisionExplainer.cs`）：`IDecisionExplainer`（MCTS 回報 `SearchSummary` → `IGameEventSink.OnSearch`）、`IScoreExplainer`（手寫策略回報每個動作的分數 → `OnScores`；`RecordScores` 只有回放 sink 會由 `GameRunner` 打開，不影響大量模擬與選擇結果）。

**`Simulation/`**
- `SeatParams.cs`：Dashboard「策略模擬」頁座位參數框的邏輯（預設值 `Defaults`、顯示順序 `Order`／`MctsFirst`、`IsDefault`、文字轉參數 `Build`、座位 id `Ids`、座位順序選項 `SeatOrders`）；`MctsFirst`、`SeatOrders` 也經 `ml/engine-info.json` 給 ML UI 用。測試 `Tests/SeatParamsTests.cs`。
- `SimulationConfig.cs`（`ParallelismConfig.ToOptions`：大量模擬與 dump 的平行迴圈都用它）、`SimulationResult.cs`（`PlayerRecord`：分數構成、`Buildings`／`BuiltRounds`、`Tiles`、金幣、出貨次數；舊檔這些欄位為 null）、`SeedDeriver.cs`。
- `GameRunner.cs`（單局＋座位分配；`CreateStrategies` 依座位建策略，`tools/leafeval`、`tools/valuenoise` 接續對局時也用它，不要在工具裡另寫一份）、`BatchSimulator.cs`（Parallel／checkpoint／取消／續跑）、`Sweep.cs`（參數掃描）、`PositionDump.cs`（價值函數的訓練資料，Runner `--dump-positions`）。
- Dashboard 用的統計（UI 無關，有單元測試）：`ResultAnalysis.cs`、`GameFilter.cs`（對局列表篩選）、`ResultComparison.cs`（兩份結果並排）、`TournamentOverview.cs`（多檔彙整、兩兩對戰矩陣）、`ResultFiles.cs`（Dashboard 選單列哪些結果檔：`results/*.json`＋`results/ml/*.json`）、`ResultSummary.cs`（結果檔轉成貼給 AI 的短 Markdown，Dashboard 結果頁「複製摘要給 AI」用；文字由呼叫端的查表函式給（`ToMarkdown(r, a, L.T)`，鍵 `sum.*` 在 `i18n/dash.*.json`，測試用 `Tests/ResultAnalysisTests.cs` 的 `DashText` 讀同一份），引擎不寫死任何語言；ML UI 有對應的 Python 版 `modelmeta.match_summary`／`dump_summary`／`train_summary`，欄位風格要一致）。

**`Events/`**：`IGameEventSink`、`NullEventSink`（大量模擬）、`ListEventSink`（回放）。

## 常見修改
- **改／加規則**：先改 `rules.md` → `Game/Rules.<階段>.cs` 的 `Fill*`／`Apply*`；數字改 `Buildings.cs`／`GameConstants.cs` → 在對應 `Tests/*Tests.cs` 加情境測試（註明 rules.md 節次）→ `dotnet test -c Release`（fuzz 會檢查不變量）。新增動作種類要同步 `ActionType`、`GameAction.ToString`。
- **加手寫策略**：繼承 `HeuristicStrategy`，只覆寫要改的掛鉤，加進 `StrategyRegistry.HandWritten`（一行；自動成為 `rule-based` 的 profile）（範本 `HarborRushStrategy.cs`）；測試放 `Tests/StrategyTests.cs`。
- **加其他策略**：實作 `IStrategy`（座位＝`state.Actor`，亂數只用工廠給的 seed，不得讀對手 `VpChips`）→ `StrategyRegistry.Factories` 註冊 → 加測試（至少跑完 100 局不丟例外）。
- **加／改任何策略後**：同步 `Dashboard/Services/StrategyInfo.cs`（`Ids`、`GroupIds`）、`Dashboard/Services/Palette.cs`（顏色）、`i18n/dash.*.json` 的 `strat.<id>.*` 與 `i18n/ml.*.json` 的 `strategy.<id>`；漏了 `ml/tests/test_i18n.py::test_every_strategy_has_its_texts_and_a_colour` 會失敗。ML UI 的策略清單讀 `ml/engine-info.json`，不用改。
- **加可掃參數**：手寫策略在 `Configure(players)` 用 `Param(名稱, players, 3人預設, 4人預設)` 讀；其他策略在建構子用 `StrategyRegistry.GetDouble`。
- **參數掃描**：設定檔加 `sweep: { target, gamesPerPoint, parameters: { 名稱: [值…] } }`（只掃數值，笛卡兒積），Runner 加 `--sweep`；每個格點同一個主種子，只比 target 的勝率（95% 信賴區間）與平均分。
- **改設定／結果 JSON 欄位**（先問使用者）：新欄位給預設值以相容舊檔，破壞性改動遞增 `SchemaVersion`；同步 `config.example.json` 與 `BatchSimulator.EnsureCompatible`。

- **改了引擎或策略的程式**：跑 `dotnet test`，`GoldenTests`（`Tests/VersionTests.cs`、`Tests/Data/golden.json`）會分開報告：RULES 案例（只有隨機玩家）變了＝規則或亂數 → 建議規則版本 `EngineInfo.RulesRevision` +1；某策略的案例變了且預設參數沒變＝它的決策邏輯變了 → 建議 `StrategyRegistry.Revisions["<名稱>"]` +1；只有預設參數變了 → 不進版本（完整參數已在 hash 裡）。**先告訴使用者並建議版本號**，同意後改常數、在 `docs/versions.json` 補對應的筆數（引擎版本至少次版本 +1）、`PR_UPDATE_GOLDEN=1 dotnet test --filter Golden` 重產生 `golden.json`、`ml/strategy-params.json` 與 `ml/engine-info.json`、在 `docs/TODO.md` 記哪些資料與模型因此該重產生。黃金樣本不含 MCTS：只動 MCTS、估值模型推論或特徵集程式時要自己判斷 `mcts` 要不要加 1。完整規則在根目錄 `CLAUDE.md`「版本與 hash」。
- **參數**：策略一律用 `StrategyRegistry.GetDouble`／`GetString` 讀參數（`Resolve` 靠它們記錄實際使用的值；直接讀字典的參數不會進結果檔與 hash）；要等知道人數才讀的，實作 `IResolvesParameters`（`HeuristicStrategy` 已實作）。
- **加策略**：除了註冊（手寫策略進 `HandWritten`，其他進 `BuildFactories`），在 `StrategyRegistry.Revisions` 給 1、`docs/versions.json` 的 `strategies` 補一條、重產生黃金檔（`Every_Strategy_Has_A_Revision` 與版本清單測試會檢查）。
- **新增功能、輸出欄位**：建議引擎版本次版本 +1，並在 `docs/versions.json` 補一筆。`EngineInfo.Commit` 來自組件的資訊版本（`Directory.Build.props` 的 `SetSourceRevisionId` 在建置時呼叫 `git describe`；沒有 git 時是 `unknown`），只用來追溯，不進 hash。續跑（`--resume`）會拒絕規則版本、策略版本或預設參數不同的結果檔（`BatchSimulator.EnsureSameBehaviour`）。

## 架構決策（不要改回去；要推翻先討論）
- 策略介面固定為 `GameAction ChooseAction(GameState state, IReadOnlyList<GameAction> legalActions)`，隨機／手寫／MCTS 共用，不另開介面。
- 決策點＝狀態＋合法動作清單；引擎提供 Clone／GetLegalActions／Apply／IsOver／Score；策略不直接改狀態。
- `GameState` 不放 List／Dictionary／字串（Clone 要快）。牌疊以各種類張數＋`RngState` 表示，不存牌序。
- `Apply` 之後自動推進到下一個真正的決策（沒有動作或只剩 Pass 的人略過）；唯一合法動作（非 Pass）由 `GameRunner` 依 `options.autoAdvanceForced` 直接套用。不要在策略端或測試裡自己迴圈略過。
- Mayor 放置「依 slot 非遞減順序逐一放」，並剪掉無法放滿的選項（每種分配只對應一條動作序列）。
- 平行用 `Parallel.For`；大量模擬不開事件記錄。
- 種子：gameSeed＝SplitMix64(masterSeed, gameIndex)；策略亂數由 (gameSeed, seat) 衍生；結果與執行緒數無關。不要改成每執行緒一個 Random。
- `seatOrder`：`random`（預設）、`balanced`（3 人 6 種／4 人 24 種排列輪流，局數為 6／24 的倍數時完全平衡）；`rotate`、`fixed` 不建議。
- 隱藏資訊（對手 VP 籌碼）：照傳完整 `GameState`，約定策略不得讀對手 VP（MCTS 內部除外）；不做遮罩副本。
- 座位 ID（起始種植園綁座位）與「當前總督」分開追蹤；金幣無上限，貨物與殖民者有嚴格上限。

## 容易踩的雷
- `GameState.RngState` 只在抽種植園時推進：複製後兩份狀態會抽到相同的牌；MCTS 每次 rollout 必須先 `ReseedRng(新種子)`。
- 玩家陣列固定開 4 個座位，3 人局第 4 座位全是 0：迴圈與模數用 `s.PlayerCount`、`s.RoleCount`、`s.ShipCap`；`GameConstants.XXX(players)` 是依人數查的函式。
- 手寫策略預設參數依人數不同，且在第一次 `ChooseAction` 才解析；`StrategyTests` 多半是 3 人局，用到 4 人預設值（如 premium 的 `switchRound`、harbor 的 `harborReadyTiles`）要明確傳參數。設定檔寫明的參數永遠優先。
- 隨機玩家座位 3（玉米起手）勝率約 49% 不是 bug（三家都改染料起手後各 33%）。
- 特徵集並存：模型檔記著訓練時的特徵名稱，載入時 `FeatureSets.Find` 依名稱挑對應的集（`IValueModel.Features`），MCTS 與 dump 都用那一套；名稱不屬於任何已知版本才會被拒。**一個特徵版本一經有模型或資料就不要再改**（改了舊檔就對不上）：要換特徵清單就新增 `FeaturesV{N}.cs`、登錄進 `FeatureSets.All`、`LatestVersion` 加 1，新版寫成「舊版原樣＋新特徵」最省事（`FeaturesV2` 呼叫 `FeaturesV1.ExtractAll` 再填後面）。測試鎖住版本 1 模型的對局不變（`ValueModelTests`），新版要補名稱、取值、dump 與載入的測試（`FeatureSetTests`）。
- 長時間的 Runner 背景工作用發佈版（`dotnet publish Runner -c Release -o publish/runner` 後執行 `./publish/runner/Runner`，Windows 是 `publish\runner\Runner.exe`）；用 `dotnet run` 跑時不要同時 `dotnet build`（會覆寫執行中的 dll）。發佈版不會自動跟著 Engine 更新：改了 Engine 要重新發佈。
- 測試建情境用 `Tests/Sc.cs`（`New`、`Start`、`Own`、`SetTiles`、`SetGoods`、`Legal`、`A`）。
