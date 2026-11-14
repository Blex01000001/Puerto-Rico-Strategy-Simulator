# TODO — 目前狀態

記錄專案目前的待辦、已知問題與想法。標記：【直接做】使用者點名就能動手；【先討論】會改架構／輸出格式／引入新工具或方向未定；【使用者】需使用者自己操作。維護規則見 `CLAUDE.md`。開工前讀「待辦」即可；「已知問題／限制」與「想法」在相關工作時再查。

## 待辦

目前以 4 人局為主：3 人局的議題（調參、模型、實驗）一律先擱置，記在下方「擱置」。

1. 【先討論】cheap-engine 的 `roleCoinWeight` 預設要不要改成 4 人局 2、3 人局 2.5（分析文件第 9 節：四桌勝率 +6～+14 個百分點，對 MCTS 的差距少約 26 個百分點）；改了之後 `tournaments/` 含 cheap-engine 的桌子、第 1、2 節與 README 的數字都要重跑。
2. 【先討論】cheap-engine 其餘弱點（第 9 節）：貨爛掉太多（每局 4～5 桶，早買小倉庫或少生產靛藍）、小市場買了幾乎不賣、菸草／咖啡種植園不蓋工廠、建築只買到第 2 階、前期少選 Craftsman／Mayor；其他手寫策略的 `RoleCoinWeight` 也都只有 1～1.6，可用同樣方法（`tools/sparring`）各掃一次。
3. 【先討論】手寫策略其他方向：corn-shipper 的玉米／Settler 估值偏低（只搶種植園的變體比它強，分析文件 7.4），可調高後重測；premium 避開被搶種植園的做法（前期不搶玉米的實驗沒有幫助）。
4. 【先討論】MCTS 擴充：更大的模擬次數、rollout 的職業選擇不再完全隨機、MCTS 自我對戰的深入分析；搜尋樹重用在現有介面做不到（見分析文件第 5 節）。
5. 【直接做】Dashboard 擴充：「策略模擬」頁加續跑；模擬重播可加兩局並排。

### 機器學習（`ml/`，分析文件第 10 節）
目前：4 人局 v2／v3（LightGBM）同時間對原版 MCTS 約 65%／32%、對手寫 91～95%，第二輪自我對戰（v3）沒有再進步；MLP v2（PyTorch）與 LightGBM v2 一樣強。工具：ML UI（Streamlit，`ml/ui.py`，另外啟動）、背景工作、`.meta.json`、Dashboard 價值模型下拉選單、RunPod 腳本（`docs/runpod.md`）都已完成。

6. 【先討論】4 人局再進步的方向（v3≈v2，多迭代已經沒有用）：更多模擬次數、更大的模型或新特徵（例如對手可能選的職業）、用更多模擬次數產生較高品質的自我對戰資料。
7. 【先討論】要不要把 4 人局模型（v2）設成 `mcts` 的預設（改了第 5、7、9 節含 MCTS 的 4 人局數字都要重跑）。

### 擱置（使用者指示，暫不處理）
- RunPod 實測：在真正的 pod 上照 `docs/runpod.md` 跑一次（`setup.sh --test`、`start.sh`、SSH 通道、帶回模型）；視需要加 `--summary-only` 之類的輸出選項。
- 推論成本：更少／更淺的樹、更小的 MLP，比同時間勝率（MLP 256-128 比 LightGBM 慢 1.5～3 倍）；選做：勝負模型（回放顯示真實勝率估計）、`leafRollout` 0 對 20、用 v2 當陪練找手寫策略弱點。
- 3 人局模型：3p-v3（兩輪自我對戰）對原版 53.5%／36.9%，但對手寫桌仍不如原版 MCTS（55.8% 對 67.5%，平均分波動大）；可試第三輪自我對戰、`leafRollout`、3 人局專用特徵；3 人局要不要用 3p-v3 當預設。
- 3 人局手寫策略：build-first 在新同分預設下變弱（第 2 節），可依對手調整採石場策略（8.6）；cheap-engine 的 3 人局另外調參。

## 已知問題／限制

- `wharf-rush` 在這份實作下偏弱（4 人局約 18%、3 人局約 39%）：Wharf 平均到第 9～10 回合才買到；MCTS 陪練（random 或 wharf-rush rollout）都不買 Wharf、也打贏它，目前沒有證據顯示 Wharf 太強（分析文件 7.2）；前期金幣來源的參數掃描在 4 人局沒有進步（7.1）。`wharf-premium`（菸草／咖啡籌錢）也沒有更強（7.5）。`corn-monopoly` 的搗亂效果已量化並拆成兩種手段（7.3、7.4：囤貨比搶種植園傷，且大部分落差只是多一個玉米玩家）。

- Dashboard 的 ML UI 啟動在 Linux 驗證過（啟動、狀態、缺套件的錯誤訊息）；Windows 上已能啟動，但多個 Python 時曾裝錯地方（`No module named 'lightgbm'`），改成挑套件齊全的 Python 並印出修正指令後還沒在 Windows 實測。
- ML UI 只在 Linux（Chromium）實際操作驗證過；Windows 上的背景程序（`DETACHED_PROCESS`）、`start-ui.cmd` 與 Ctrl+C 後工作繼續執行，還沒在 Windows 實測。Windows 上取消資料／對戰工作是直接結束 Runner（沒有共用的主控台可送 Ctrl+C），不會保留已完成的局數。
- 策略模擬頁（`Simulate.razor`）的「完全平衡」選項與局數提示、局數千分位輸入、MCTS 耗時警告、自訂結果檔名、策略下拉選單名稱只通過編譯與單元測試，沒有在瀏覽器實際操作驗證（驗證時環境的安全檢查擋下了 Playwright 指令）；下次開 Dashboard 時順手點一次。
- 分析文件第 1、2、7 節的數字是 `balanced` 座位 + 新同分預設（`tournaments/` 4 人 100,008／3 人 100,002 局）；第 3～4 節的調參與第 5 節 MCTS 實驗是舊預設下做的（第一到第三輪調參是 `rotate`、未重跑，MCTS 的對手 build-first／harbor-rush 也是舊同分順序）；總覽頁的「座位順序」欄會標示每份結果用哪種。
- 陪練實驗（第 9 節）MCTS 每桌只有 480 局，勝率誤差約 ±4 個百分點；`tools/sparring` 不在 `PuertoRico.sln`，改了 Engine 後要另外 `dotnet build -c Release tools/sparring`（否則會用到舊的 Engine）。
- 規則中未明說、引擎採用的詮釋（請使用者確認，或提供反例）：
  - Factory 的金幣依「公式產量 > 0 的貨種數」計算，不看實際領到多少（供應不足時也照給）。
  - Guild Hall／City Hall 計算的建築不要求有殖民者（只有大型建築本身要）；可由 `Scoring.CountedBuildingsNeedColonist` 切換。
  - Craftsman 特權可選的貨種 = 公式產量 > 0 的貨種（即使供應區已空，那時只是拿不到）。
  - 倉庫保留：玩家一律完整保留 min(倉庫可保留種類數, 持有種類數) 種（保留更多不會變差），再選 1 桶；引擎不提供「少保留」的選項。
  - Hacienda 盲抽時牌疊已空：先把棄牌洗回再抽（規則只寫了翻牌時的洗牌）。
  - 市長階段是逐位玩家把全部殖民者拔起再放（先輪到的人先放）；結果與同時放置相同。
- 結果記錄不含「各職業被選次數」（Prospector 偏好等要另外統計）與「每個建築是否有派殖民者」。
- 規則：隱藏資訊（對手 VP）只靠約定，沒有機制阻止策略讀取。
- 續跑（`--resume`）需要 `output.perGameRecords: true`；結果檔約 700～900 bytes／局（10 萬局：3 人局約 70 MB、4 人局約 89 MB）；舊版本（沒有建築清單）的結果檔仍可在 Dashboard 檢視，但不能 `--resume`。
- 手寫策略的對戰結論見 `docs/strategy-analysis.md`；3 人與 4 人階層不同（4 人局 build > harbor > premium > corn，3 人局 harbor ≈ premium > build > corn；random 座位）；手寫策略的預設參數依人數分開（3 人局另外調過，`HeuristicStrategy.Configure`／`Param`）。座位優勢仍在（4 人局座位 1／2／3／4 勝率約 17%／24%／37%／23%）。
- 引擎玩家數 3 或 4（`players`）；5 人局與擴充不支援。4 人局職業 Prospector 在手寫策略裡的估值很簡單（約等於 1 枚金幣）。
- 沒有 lint 工具（`dotnet format --verify-no-changes` 可用）。Dashboard 沒有自動化測試（Tests 只參考 Engine）；以 Playwright 截圖驗證過三個頁面（淺色／深色）。分析邏輯在 `Engine/Simulation/ResultAnalysis.cs`，有單元測試。
- 價值模型的推論成本與一次 8 回合隨機 rollout 同級（LightGBM 400 棵樹約 20 µs、MLP 256-128 約 30 µs，每個座位一次），所以同樣模擬次數下時間沒有省；模型依人數分開，目前只有 4 人局。
- MCTS 比手寫策略慢很多（4 人局預設 300 次模擬、截斷 8 回合：400 局約 92 秒，4 核心），只適合數百局的實驗；它看得到完整狀態（含對手 VP），不偷看牌堆（每次模擬重洗）；實驗結果在 `docs/strategy-analysis.md` 第 5 節，設定在 `mcts/`。
- Dashboard「模擬」頁可跑一般對戰與參數掃描，但沒有續跑；比較頁只比一般結果檔的勝率與平均分（不比建築等細項），顯著性假設兩份獨立，一個瀏覽器分頁同時一個任務；模擬與 Dashboard 同一程序，跑大量局數時建議仍用 Runner。
- Dashboard 會把整份結果檔讀進記憶體（10 萬局約 50 MB 沒問題，百萬局以上要改成只讀摘要），並可讀取伺服器上任意路徑：只在本機執行（預設綁 localhost:5080），不要對外開放。
- 效能：4 核心約 21,000 局／秒（約 5,000 局／秒／核心，隨機玩家，一局約 500 個決策）。
- 隨機玩家下座位 3（玉米起手）勝率約 49%，座位 1、2 各約 24%；已驗證不是引擎不對稱（三家都改染料起手後各 33%）。
- SessionStart hook 已在 main；其「dotnet 不存在時 apt 安裝」分支在已安裝的容器中無法重測（新 session 若沒有 dotnet，請確認 hook 有執行，必要時手動 `apt-get install -y dotnet-sdk-8.0`）。
- `builds.dotnet.microsoft.com` 被這個雲端環境的網路代理擋住，`dotnet-install.sh` 在這裡不可用，只能用 apt 安裝 .NET（RunPod 上 `deploy/runpod/setup.sh` 會在 apt 失敗時改用它）。

## 想法

- 手寫策略同分的第二準則：機制在 `tieTile`／`tieGood`／`tieRole`／`tieBuild`（分析文件 8.2）；build-first、harbor-rush、wharf-rush 預設「糖先於靛藍、玉米先於採石場」（8.3，`DefaultTieTile`，`tieTile: ""` 關閉）；其他策略實測引擎順序已是最好或無差別（8.4、8.5：貨物、建築、選職業、出貨同分），不設預設。剩下的同分都只有零星幾次；特徵權重版本（貨價、建築費用、`tieOpponent` 等）之後再加。
- build-first 3 人局 `quarryTarget` 的最佳值取決於對手（8.6）：對沒有 cheap-engine 的桌子 1 較好，有 cheap-engine 時 1 崩盤、2～3 較好；若要改需依對手動態決定或接受取捨。
- 對局列表只能用結果檔現有欄位篩選；要篩「終局手上貨物、殖民者有沒有派下去」或「某步發生過什麼」需要新增記錄欄位（先問）。重播後比對名次與分數、重播結果存附屬檔案都還沒做。

- Dashboard：策略顏色目前依策略名稱固定對應前 5 個色票（藍、橘、青、黃、洋紅），超過要定義更多色票或改用小倍數圖。
- 參數掃描目前是網格搜尋、對手固定；可考慮多目標座位同時掃、或交替調參（調 A 對固定 B，再調 B 對新 A）。

- 結果檔過大時，`games` 另寫 JSONL，主檔只放 summary。
- Dashboard 內建單局回放檢視（Runner 的 `--replay N` 已能輸出決策記錄）。
