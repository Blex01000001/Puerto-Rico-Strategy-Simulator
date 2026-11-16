# ml/（學習型局面價值函數：訓練端）

Python 子專案：產生資料用 Runner（C#），訓練在這裡，推論在 Engine（C#）。讀到這個資料夾的檔案時自動載入；全專案規則在根目錄 `CLAUDE.md`，流程與指令在 `ml/README.md`。

## 檔案地圖
- `positions.py`：讀 Runner 的 dump（`.bin`＋`.bin.json`）；`expand`（萬用字元／資料夾展開）、`read_meta`（格式、版本檢查）、`load`（多檔需同特徵清單、`featureVersion`、人數）、`split`（依局切驗證集）。
- `modelmeta.py`：`<模型>.meta.json`（參數、資料來源、驗證成績、特徵重要度、環境、`matches` 對戰勝率）；`write`／`read`／`match_entry`／`add_match`／`move_model`。正式模型（`ml/models/`，git 追蹤）的對戰紀錄寫在 `ml/local/match-records/<模型>.matches.json`，`read` 時合併（標 `local: true`），追蹤中的 `.meta.json` 不會被改；本機模型直接寫進自己的 `.meta.json`。
- `fingerprint.py`：**配方 hash**。同一組參數（配方）一定得到同樣的檔案（引擎對設定與種子是確定的），所以配方的 SHA-256 能回答「這兩份是不是一樣」，配方本身能回答「差在哪」（`describe`：局數 20,000 → 200,000、座位 2 的策略版本 build-first：v1 → v2…）。配方內容（`HASH_FORMAT` 2）：資料＝規則集（`base`）與規則版本、預留的 `variant`／`variantOptions`（目前空）、人數、已打局數、種子、抽樣率、座位順序（小寫）、每個座位的策略、**策略版本**（`revisions`，MCTS 含 rollout 策略）與**完整參數**（預設值已填；`valueModel` 換成**檔案內容** hash；依座位順序）、`limits`、`options`、dump 格式版本、特徵版本；模型＝種類、特徵版本、各份資料的 hash、訓練參數（白名單 `LGBM_OPTIONS`／`MLP_OPTIONS`；`threads` 不算，MLP 的 backend／device 用解析後的值）；對戰＝同資料但沒有抽樣率與特徵版本。**不算**：檔名、設定檔名稱、座位 id、執行緒數、引擎版本與 git commit、套件版本（只記錄與顯示）。完整參數：有 `resolvedSeats` 的檔案（引擎 0.3.0 起）直接用；沒有的舊檔用**凍結**的 `ml/strategy-params.legacy.json` 補算（`resolve_seat(..., legacy=True)`，永遠不要重產生）；還沒執行的（UI 預測）用 `ml/strategy-params.json`（引擎產生、C# 測試保證與程式一致）。`resolve_seat` 要與 C# 的 `StrategyRegistry.Resolve` 一致（rule-based＝它的 profile 加 `profile` 參數、MCTS 加 rollout 策略的版本；`tests/test_runner_jobs.py` 用真的 Runner 比對預測與實際的 hash）。`stale_notes` 列出比目前程式舊的規則與策略版本（UI 的「版本狀態」）。ML UI 一律說「hash」，不說「指紋」。規則版本顯示成 `base-vN`（`rules_name`），策略版本 `harbor-rush-vN`（`strategy_name`）；`load_versions` 讀 `docs/versions.json`（`strategies=True` 取策略版本）。**改配方內容（遞增 `HASH_FORMAT`，先問使用者）、新增參數時要同步「hash 說明」頁（`hash_page`，參數清單大多從 `fingerprint` 的常數產生）與版本清單；版本號的規則在根目錄 `CLAUDE.md`「版本與 hash」。**舊檔缺的欄位用預設值補（`rulesRevision` 1、`rulesVersion` base、`limits` 150／20000、`autoAdvanceForced` true）；舊模型沒有 hash（標「舊紀錄」）。`current_rules_revision`／`current_feature_version`／`current_format_version`／`current_engine_version` 直接讀 C# 原始碼的常數，`current_strategy_revision` 讀 `ml/strategy-params.json`。
- `model_report.py`：所有模型（正式＋本機）的勝率摘要表，給 `docs/models.md` 用（數字一律從這裡取）。
- `train_lgbm.py`、`train_mlp.py`：`train(data, out, progress=None, log=print, **options)` 可匯入（ML UI 用），命令列只是包一層；都寫 `<模型>`、`.meta.json`、`.check.txt`。
- `ui.py`：ML UI（Streamlit，`streamlit run ml/ui.py`；左側導覽（Dashboard 樣式）：頁面「模擬對局採樣」「模型訓練/蒸餾」「對戰驗證」「模型清單」「排程佇列」「hash 說明」「版本控管」列在 `PAGES`（名稱在 `TAB_*` 常數），一次只畫目前那一頁；目前頁記在 `session_state["page"]` 與網址 `?page=`（重新整理不跳頁）；導覽最下方是 `sidebar_status`（只顯示正在跑的工作，排隊數用小字）。）。版面：每區一張卡片 `card(key, title)`（`st.container(border=True, key="card-…")`，樣式在 `CSS`）；所有開始鈕用 `action_row`（藍色可按、鎖住時右邊紅字寫原因、有工作在跑時寫排第幾個）；刪除用 `delete_button`（確認後才刪，排隊或執行中的工作要用的檔案不能刪）；參數格 `param_inputs` 在 `st.container(key="params")` 裡，標題統一兩行高；參數說明表 `PARAM_DOC`（加訓練參數時一起補）。主題色在根目錄 `.streamlit/config.toml`（與 Dashboard 同色票）。啟動檔 `start-ui.sh`／`start-ui.cmd`（綁 localhost:8501、隱藏 Deploy 鈕）。路徑一律顯示成相對專案根目錄（`rel`／`scrub`，與 Dashboard 相同規則）。
- 工作種類（`job_runner.py`）：`train_lgbm`／`train_mlp`（取消＝結束程序）、`dump`、`match`（呼叫發佈版 Runner `dotnet publish/runner/Runner.dll`，`PR_RUNNER_DIR` 可改；原始碼較新會先自動發佈；從輸出解析 `n/total games` 當進度；取消送 SIGINT，Windows 直接結束；`match` 完成後 `modelmeta.add_match`）。UI 寫的東西一律進本機工作區 `ml/local/`（被 git 忽略）：訓練的模型 `ml/local/models/`、自訂組合與自我對戰設定 `ml/local/data-configs/`（同名已存在就拒絕，內建的 `ml/data-configs/` 也算）、對戰設定 `ml/local/matches/`；模型名稱在正式與本機之間不能重複（`model_path` 用檔名找）。「模型清單」可以「重新命名」（只限本機模型：`modelmeta.rename_model` 一起改三個檔與 `.meta.json` 裡的名稱；排隊或執行中的工作要用它時不能改；`model_name_users` 列出還用舊名字指向它的資料與設定檔並警告）、「設為正式模型」（本機→`ml/models/`，之後 commit 並更新 `docs/models.md`）或「移到本機」（`ml/models/` 裡 git 沒追蹤的）。「自訂組合」的策略清單直接從 `Engine/Strategies/StrategyRegistry.cs` 讀（`strategy_names`，排除需要 profile 的 `rule-based`），新增策略不用改 UI；中文說明在 `STRATEGY_TEXT`（沒有的就只顯示名稱）。
- `jobs.py`：背景工作（`results/ml/jobs/<id>/`：`job.json` 狀態與心跳、`events.jsonl` 進度、`log.txt`、`cancel` 旗標檔）；`start`（沒有工作在跑就馬上開始，否則狀態 `waiting` 排隊）／`start_next`（啟動最早排隊的那個；有工作在跑就不動）／`cancel`（排隊中的直接標成取消，執行中的放 `cancel` 旗標）／`list_jobs`／`active_job`／`waiting_jobs`／`queue_position`／`events`／`wait`。一次只跑一個；每個工作結束（完成、失敗、取消）時 `job_runner` 呼叫 `start_next`，所以關掉 UI 佇列也會繼續；程序被硬殺而沒交棒時，UI 的 `watch_states` 會補叫 `start_next`。`.dispatch.lock`（排他建立的鎖檔，超過 60 秒視為殘留）保證不會同時啟動兩個。狀態：`waiting` 排隊中、`queued` 啟動中、`running`、`done`、`failed`、`cancelled`、`lost`（心跳過期但程序還在：佇列暫停等它，`cancel` 會強制結束它與 Runner 再派下一個）、`interrupted`（心跳過期且程序已不在）。佔住佇列的狀態集中在 `jobs.BUSY`，判斷「有沒有工作在跑」一律用它。程序存活用 `process_alive`（`job.json` 的 `pid`＋`startedEpoch`：還要是 Python／job_runner、建立時間不晚於工作開始，避免 pid 被別的程式重用時誤判；Windows 用 kernel32，Linux 讀 `/proc`，殭屍程序算已結束）。`job_runner.py`：在獨立程序執行一個工作（POSIX `start_new_session`、Windows `CREATE_NEW_PROCESS_GROUP|DETACHED_PROCESS`），心跳執行緒看到 `cancel` 就結束程序。
- `data-configs/`：內建的產生資料設定檔（手寫混桌、隨機、`4p-selfplay-*`＝MCTS＋模型自我對戰）。
- `local/`（不進 git）：本機工作區，見上；在雲端 session 裡看不到使用者電腦上的這個資料夾。
- `models/`：正式模型＋`.meta.json`＋`.check.txt`（進 git）；總表與狀態在 `docs/models.md`。早期模型的 `.meta.json` 是補寫的（`params.note`、`training.note` 會註明）。
- `tests/`：pytest（`conftest.py` 產生假 dump）：`python3 -m pytest ml/tests`。`test_runner_jobs.py` 需要 .NET SDK（沒有就略過），會把 Runner 發佈到暫存資料夾。
- `requirements.txt`：`python -m pip install -r ml/requirements.txt`。
- `check_env.py`：這個 Python 有沒有 ML UI 的套件；沒有就印出該 Python 的完整路徑與 `"<python>" -m pip install -r …`（退出碼 1）。`start-ui.cmd`／`.sh`、`ui.py`（缺套件時只顯示修正指令）、Dashboard 的啟動按鈕都用它；必要套件清單在 `REQUIRED`（加套件時同步 `requirements.txt`）。
- `make_test_fixture.py`：重產 C# 測試用的小模型 `Tests/Data/tiny-lgbm.*`（改特徵後要跑）。

## 契約（兩邊要一起改）
| 契約 | 定義在 | 讀的人 |
|---|---|---|
| 特徵清單（名稱、順序、`featureVersion`） | `Engine/Strategies/Mcts/ValueFeatures.cs` | dump、`positions.py`、模型（訓練時寫入特徵名稱）、C# 推論（載入時逐一比對） |
| dump 格式（`formatVersion`、紀錄排列） | `Engine/Simulation/PositionDump.cs` | `positions.py`（`FORMAT_VERSION`、`record_dtype`） |
| 模型格式（LightGBM 文字檔、MLP JSON） | 訓練腳本寫出 | `Engine/Strategies/Mcts/ValueModel.cs` |
| 配方 hash 的內容（上面 `fingerprint.py`） | `ml/fingerprint.py`；C# 端的 `EngineInfo.RulesRevision`、`StrategyRegistry.Revisions`／`Resolve`、`.bin.json` 與結果檔的 `rulesVersion`／`rulesRevision`／`resolvedSeats`／`limits`／`options`；`ml/strategy-params.json`（C# 產生）與凍結的 `ml/strategy-params.legacy.json` | `modelmeta.py`（寫進 `.meta.json` 的 `fingerprint`／`recipe`／`rulesRevision`、各資料的 `fingerprint`、各對戰的 `fingerprint`／`modelSha256`）、ML UI |

## 常見修改
- **改特徵**：改 `ValueFeatures.cs`（遞增 `Version`）→ 重新產生所有資料 → 重訓；舊模型在 Engine 會被拒（刻意）。`Tests/Data/tiny-lgbm.*` 也要用新資料重產：`python3 ml/make_test_fixture.py results/ml/<任一新 dump>.bin`。
- **改 dump 格式**：C# 遞增 `PositionDump.FormatVersion`，同步 `positions.FORMAT_VERSION` 與 `record_dtype`，兩邊測試一起跑。
- **加訓練參數**：加進 `DEFAULTS`、`train()` 的 `params`（會寫進 `.meta.json`）與 argparse；**同步 `fingerprint.LGBM_OPTIONS`／`MLP_OPTIONS`**（影響模型的放白名單，不影響的放 `IGNORED_OPTIONS`；`tests/test_fingerprint.py` 會在漏掉時失敗）；測試在 `tests/test_train.py`。
- **改 hash 的內容**（新增或移除進配方的欄位）：所有舊 hash 會變成「不同」，改前先問使用者；舊檔缺的欄位要有預設值（見 `DEFAULT_LIMITS`）。
- **新模型種類**：Engine 要先能推論（`ValueModel.cs` 加類別＋與 Python 一致的測試），再寫訓練腳本；輸出格式不變的改寫（例如 MLP 改 PyTorch）只要 `.check.txt` 與 C# 比對一致。
- **ML UI 加頁面或工作種類**：工作種類加進 `jobs.KINDS` 與 `job_runner.run`（產生資料、對戰要呼叫發佈版 Runner：`publish/runner/Runner`，進度從 Runner 輸出解析）；頁面加進 `ui.py` 的 `PAGES`（id、名稱、圖示、函式、分組標題）；需要即時更新的區塊用 `@st.fragment(run_every=...)`，工作狀態改變時整頁 `st.rerun(scope="app")`（`watch_states` 的做法）。測試：`tests/test_jobs.py`（真的開程序）、`tests/test_ui.py`（`AppTest` 無頭執行；一次只畫一頁，用 `goto(at, "<id>")` 點導覽）；畫面用 Playwright 截圖確認（Streamlit 的表格是 canvas，勾選列要點座標）。
- **新增或刪除正式模型**：三個檔一起動（`modelmeta.move_model` 或 git），用 `python3 ml/model_report.py` 取數字更新 `docs/models.md`（刪除的保留一列、狀態改「已刪除」）。
- **對戰結果記到模型**：`modelmeta.add_match(<模型>, <Runner 結果檔>)`（同一結果檔重覆加只會取代）。

## 雷
- 訓練資料很大（約 870 bytes／列）：LightGBM 會轉成 float32（257 萬列約 4.4 GB），MLP 保持 int16 逐批標準化；不要在 MLP 先整份轉 float（第一次就因記憶體不足被系統停掉）。
- 驗證集 MSE／R² 和勝率對不上（資料分布換了 R² 就會變），判斷模型只看對戰勝率（`matches`）。
- 長時間產生資料用發佈版 Runner（`./publish/runner/Runner`），見 `ml/README.md`。
- Streamlit 的 header 會蓋住頁面頂端：`.block-container` 的 padding-top 不要小於約 2.9rem（太小標題會被切掉）。表格（dataframe）不能放按鈕：要逐列操作就用勾選＋一個按鈕（`delete_button`），或用 `st.columns` 自己畫列（`queue_page`）。
- 深色主題的輸入框底色（`secondaryBackgroundColor`）和卡片同色、又沒有框線，輸入框會整個看不見：`CSS` 裡另外把輸入框、下拉選單、數字框、單選群組（`stRadioGroup`）、指標（`stMetric`）改成較深的底色＋`#333a4b` 框線（聚焦時藍框）。Streamlit 1.6x 起文字框與下拉選單改用 react-aria（`data-testid="stTextInputRootElement"`、`.react-aria-ComboBox`），沒有 `data-baseweb` 了；舊版仍是 baseweb：選擇器兩種都要列（只寫 baseweb 時文字框、下拉選單沒框，數字框卻有）。新增元件種類或升版後用截圖確認。
- 刪除鈕：`delete_button` 用 `st.dialog` 確認（`confirm_delete`），不要用 popover：popover 在刪除後的 rerun 仍保持開著。按鈕包在 `st.container(key="del-…")` 裡，CSS 用 `st-key-del-` 讓它紅底靠右；確認鈕 key `<key>-confirm` 也是紅色，取消鈕用 `keep-` 開頭避開紅色。刪除後 `del-gen` 加一，有勾選的表格把它放進 key（`dumps-<n>`、`cfg-table-<n>`）：否則舊的勾選（列號）會指到別的檔案。新的刪除鈕 key 也要以 `del-` 開頭。
- 表格一律用 `grid()`（包 `st.dataframe`）：它多留 18 px 給水平捲軸，否則 Windows 的捲軸會蓋住最後一列；最多顯示 10 列再捲動。
- 同名檔案的檢查看配方，不只看檔名（`same_name_notice`）：配方相同→「完全相同，不需要覆寫」，不同→列出差異；被模型用過的資料覆寫時列出模型；不同名但配方相同→提示重複。覆寫（資料、模型、對戰結果）也會被「排隊中或執行中的工作要讀它」擋下（`reader_problem`，與刪除同一套規則；`job_reads` 列出工作會讀的檔案：訓練資料、對戰的模型、設定檔裡的價值模型）。工作的 spec 與 `rel(out)` 的路徑寫法要一致（`rel()` 產生）。
- 設定檔模式的局數、種子、抽樣率輸入框的 key 含設定檔名稱，換設定檔才會重新帶入預設值（以前 key 只有模式，換設定檔後種子停在上一個）。
- 模型清單頁：上方選模型（小卡用 `version_tiles`，和版本控管頁同樣式），下方「模型列表」卡有快篩（`st.pills`：位置、種類、建立日期；不選＝全部），數字欄用 `TextColumn(alignment="center")` 置中；並排比較用 `version_table(..., css="cmp")`（固定欄寬、不會出現水平捲軸），結果列標出最好的模型（`td.best`：勝率／R²／列數取最高，交叉熵取最低）。對戰紀錄表的「紀錄存放」＝git（正式模型追蹤中的 `.meta.json`）或本機（`ml/local/match-records/` 或本機模型自己的 `.meta.json`）。
- 版本控管頁的小卡與表格用自己的 HTML（`version_tiles`、`version_table`，CSS `.vtile`、`table.vtable`），外觀和 Dashboard 的版本控管頁（`app.css` 的 `.vtile`、`table.data.vtable`）一致：兩邊要一起改。
- 取消工作的按鈕（導覽最下方、排程佇列、工作詳細）key 以 `stop-` 開頭，CSS 讓它紅色；新的取消鈕照做。
- 排程佇列的每一列是 `st.container(key="qrow-<狀態>-<id>")`，CSS 畫框並依狀態給左邊框顏色，欄位順序：名稱、狀態、經過時間、進度、備註、操作（最右）；新狀態要在 `CSS` 補顏色。
- Streamlit 的元件 ID 由種類＋參數產生：不同頁面裡標籤相同的按鈕（例如三個「加入排隊」）會撞 ID 而報錯，要給 `key`。
- Streamlit 的下拉選單不會更新已顯示選項的文字：選項標籤不要放會變的狀態（`queue_page` 的「工作詳細」下拉選單只放名稱與時間）。表格裡數值欄的缺值會顯示灰色 None：要顯示「—」就先轉成文字（`models_table`）。
- 用 UI 測試資料／對戰時若有別的 Runner 背景工作正在用 `publish/runner`，啟動 UI 前設 `PR_RUNNER_DIR=<暫存資料夾>`：自動重新發佈會覆寫執行中的 dll。測完刪掉 UI 寫進 `ml/local/` 的測試檔（設定、模型、`match-records/`）。
- 背景工作的程序不跟著 UI 結束：測試或手動實驗後記得看 `results/ml/jobs/` 有沒有還在跑的；測試用的模型在 `ml/local/models/`（不會進 git，但記得清掉）。
- 編碼：Windows（繁中）預設輸出編碼是 cp950，`job_runner` 一律把 stdout／stderr 改成 UTF-8（`utf8_output`，`errors=replace`），`jobs._spawn` 也設 `PYTHONIOENCODING=utf-8`；Runner 在輸出被導向時改用 UTF-8（`Console.IsOutputRedirected`），讀 Runner 輸出時 UTF-8 解不開就用系統編碼（`decode`）。曾因「±」讓對戰工作在寫紀錄時當掉。
- Windows 上檔案被別的程序開著時 `os.replace` 會 PermissionError（UI 每 2 秒讀 `job.json`、防毒、索引都會）：`jobs._write_json` 會重試，`read_job` 也把它當暫時錯誤；心跳執行緒（`job_runner.heartbeat`）寫失敗只印訊息、不能讓執行緒結束。曾因此在約 10 分鐘後把還在跑的 dump 顯示成「中斷」。新的背景寫檔都走 `_write_json`。
- Windows 常有兩個 Python（Anaconda 與 python.org）：`pip` 裝到 A、`py`／`python` 跑的是 B，ML UI 就會 `No module named 'lightgbm'`。所以指示一律寫 `python -m pip`，啟動檔挑「第一個套件齊全的 Python」（`PR_PYTHON` 可指定），失敗時印出該 Python 的完整路徑與修正指令。
- 這個雲端環境擋住 PyTorch 的 CPU 版下載站；PyPI 的 `torch` 一定要帶 CUDA 函式庫（不帶就 import 失敗），完整安裝約 8 GB。使用者電腦裝 CPU 版即可。
- `train_mlp.py` 兩個後端（`fit_torch`／`fit_numpy`）要維持同樣的訓練規則（He 初始化、Adam＋L2、每 4 epoch 學習率減半、提早停止取最好的一輪）；匯出一律走同一段 JSON，`tests/test_train.py` 兩個後端都測（沒有 torch 就略過）並用 NumPy 從 JSON 重算 check 列。
