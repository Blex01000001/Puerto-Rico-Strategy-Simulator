# Engine（規則引擎、策略、模擬）

零 UI／Windows 相依。讀到這個資料夾的檔案時自動載入；全專案規則在根目錄 `CLAUDE.md`。

## 檔案地圖
**`Game/`**
- `GameState.cs`：可複製狀態（只有數值與固定長度陣列）。`GameAction.cs`：`ActionType` 與動作。
- `Rules.cs`：`GetLegalActions`／`Apply`／推進；`Rules.<階段>.cs`（Settler／Mayor／Builder／Craftsman／Trader／Captain）各有 `Fill*`（列合法動作）與 `Apply*`。
- `Setup.cs`、`Scoring.cs`、`Invariants.cs`、`Rng.cs`；靜態表：`Buildings.cs`、`GameConstants.cs`。

**`Strategies/`**
- `IStrategy.cs`（唯一介面）、`StrategyRegistry.cs`（名稱→工廠；`GetDouble` 讀 `params`）。
- 註冊名稱：`random`、`guided-random`、`mcts`、`corn-shipper`、`corn-to-premium`、`harbor-rush`、`build-first`、`cheap-engine`、`wharf-rush`、`wharf-premium`、`corn-monopoly`、`corn-monopoly-tiles`、`corn-monopoly-hoard`，或 `rule-based`＋`params.profile`。
- `RuleBased/HeuristicStrategy.cs`：手寫策略的共用打分基底（每個選擇打分取最高，子類別覆寫掛鉤：`TileValue`、`BuildingWanted`、`SlotValue`、各 `*RoleValue`、`RoleCoinWeight`…）。
- `RuleBased/` 子類別：`CornShipper`（玉米出貨）、`CornToPremium`（前期玉米、中後期菸草／咖啡）、`HarborRush`（先港口，後期加 Wharf）、`BuildFirst`（採石場折扣、依終局加成挑大型建築）、`CheapEngine`（便宜 1 分建築、少種植園、頻繁出貨；實驗參數 `roleCoinWeight` 預設 1）、`WharfRush`、`WharfPremium`、`CornMonopoly`（搗亂；`grab`／`hoard` 旗標分出 `-tiles`、`-hoard` 變體）。
- `RuleBased/TieBreakRules.cs`：同分的第二準則（字典式，只在主要分數完全相同時生效）。文字參數 `tieTile`／`tieGood`／`tieRole`／`tieBuild`，`tieOpponent` 預留。預設＝引擎順序；只有 build-first／harbor-rush／wharf-rush 有 `DefaultTieTile`＝`hacienda>corn>sugar>indigo>tobacco>coffee>quarry`（`tieTile: ""` 關閉）。策略的偏好寫在自己的規則裡，基底不內建「常理」。
- 實驗參數 `randomTies`（預設 0；1＝開拓者＋工匠額外貨物、2＝市長以外所有階段、3＝只有開拓者、4＝只有工匠額外貨物，同分時隨機）。
- `Mcts/MctsStrategy.cs`：UCT，`params.simulations`／`rolloutStrategy`／`rolloutRounds`／`exploration`。
- 選用介面：`IDecisionExplainer`（MCTS 回報 `SearchSummary` → `IGameEventSink.OnSearch`）、`IScoreExplainer`（手寫策略回報每個動作的分數 → `OnScores`；`RecordScores` 只有回放 sink 會由 `GameRunner` 打開，不影響大量模擬與選擇結果）。

**`Simulation/`**
- `SimulationConfig.cs`、`SimulationResult.cs`（`PlayerRecord`：分數構成、`Buildings`／`BuiltRounds`、`Tiles`、金幣、出貨次數；舊檔這些欄位為 null）、`SeedDeriver.cs`。
- `GameRunner.cs`（單局＋座位分配）、`BatchSimulator.cs`（Parallel／checkpoint／取消／續跑）、`Sweep.cs`（參數掃描）。
- Dashboard 用的統計（UI 無關，有單元測試）：`ResultAnalysis.cs`、`GameFilter.cs`（對局列表篩選）、`ResultComparison.cs`（兩份結果並排）、`TournamentOverview.cs`（多檔彙整、兩兩對戰矩陣）。

**`Events/`**：`IGameEventSink`、`NullEventSink`（大量模擬）、`ListEventSink`（回放）。

## 常見修改
- **改／加規則**：先改 `rules.md` → `Game/Rules.<階段>.cs` 的 `Fill*`／`Apply*`；數字改 `Buildings.cs`／`GameConstants.cs` → 在對應 `Tests/*Tests.cs` 加情境測試（註明 rules.md 節次）→ `dotnet test -c Release`（fuzz 會檢查不變量）。新增動作種類要同步 `ActionType`、`GameAction.ToString`。
- **加手寫策略**：繼承 `HeuristicStrategy`，只覆寫要改的掛鉤，在 `StrategyRegistry` 註冊並加進 `rule-based` 的 profile 清單（範本 `HarborRushStrategy.cs`）；測試放 `Tests/StrategyTests.cs`。
- **加其他策略**：實作 `IStrategy`（座位＝`state.Actor`，亂數只用工廠給的 seed，不得讀對手 `VpChips`）→ `StrategyRegistry.Factories` 註冊 → 加測試（至少跑完 100 局不丟例外）。
- **加／改任何策略後**：同步 `Dashboard/Services/StrategyInfo.cs`（規則文字與參數預設值；新策略要加進 `Groups`）。
- **加可掃參數**：手寫策略在 `Configure(players)` 用 `Param(名稱, players, 3人預設, 4人預設)` 讀；其他策略在建構子用 `StrategyRegistry.GetDouble`。
- **參數掃描**：設定檔加 `sweep: { target, gamesPerPoint, parameters: { 名稱: [值…] } }`（只掃數值，笛卡兒積），Runner 加 `--sweep`；每個格點同一個主種子，只比 target 的勝率（95% 信賴區間）與平均分。
- **改設定／結果 JSON 欄位**（先問使用者）：新欄位給預設值以相容舊檔，破壞性改動遞增 `SchemaVersion`；同步 `config.example.json` 與 `BatchSimulator.EnsureCompatible`。

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
- 測試建情境用 `Tests/Sc.cs`（`New`、`Start`、`Own`、`SetTiles`、`SetGoods`、`Legal`、`A`）。
