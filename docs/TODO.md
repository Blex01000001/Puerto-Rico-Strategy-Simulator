# TODO — 目前狀態

記錄專案目前的待辦、已知問題與想法。標記：【直接做】使用者點名就能動手；【先討論】會改架構／輸出格式／引入新工具或方向未定；【使用者】需使用者自己操作。維護規則見 `CLAUDE.md`。

## 待辦

1. 【使用者】補齊 `rules.md`：已有「初始設置」（起始金幣／種植園、貨物、VP、殖民者、貨船、採石場、交易所、牌疊張數）；「職業」已補（3 人局無 Prospector，共 6 職業）；仍缺全部建築表與效果原文、終局條件、計分與平手、Mayor／Captain／Trader 詳細流程。
2. 【使用者】回答 `rules.md` 第 1 節「待確認（設置）」5 項（種植園各種類張數、起始種植園是否取自牌疊、採石場是否獨立且不佔翻開名額、未拿走牌的棄置與洗回、金幣是否無限），`rules.md` 第 2 節「待確認（職業）」5 項，以及規劃中的規則歧義清單（對話中第六節，共 15 項：Mayor 配置與必須放滿、Captain 強制裝船／Wharf／倉庫保留、Trader 清空時機與價格表、Builder 折價與 University、Settler Hacienda／Hospice、終局時機、大型建築計分、平手、VP 耗盡、隱藏資訊、起始總督、卡死處理）。
3. 【先討論】確認兩項與原需求略有不同的建議：每局種子 = SplitMix64(masterSeed, gameIndex)（結果與執行緒數無關）、`seatOrder` 預設 `rotate`；確認後寫入 CLAUDE.md「架構決策」。
4. 【直接做】（步驟 0）讓新 session 自動有 .NET 8：SessionStart hook（`startup-hook-skill`）或環境 setup script，內容為 `apt-get install -y dotnet-sdk-8.0`。注意：setup script 修改環境設定可能需使用者核准；hook 需 commit 進 repo。驗收：新 session `dotnet --version` 可用。
5. 【直接做】（步驟 1，待 1～3 確認後）建 `PuertoRico.sln`、Engine/Runner/Tests（Dashboard 先放空殼或不建）、`Directory.Build.props`、`.gitignore`；相依方向 Runner/Tests → Engine。驗收：`dotnet build`、`dotnet test` 通過。
6. 【直接做】後續實作依序：靜態表＋GameState＋Clone → Setup → 決策流程骨架 → 各職業（Settler→Builder→Craftsman→Trader→Captain→Mayor→Prospector）→ 終局計分 → 隨機玩家＋單局執行器 → 批次模擬（Parallel.For／checkpoint／Ctrl+C／`--resume`）→ Runner CLI 與結果 JSON → 效能基準。每步驗收標準見對話規劃第八節。

## 已知問題／限制

- repo 目前只有 README.md 與本文件、CLAUDE.md，沒有任何程式碼或測試，快速檢查（build/test）尚無法執行。
- 雲端容器的 dotnet 為手動 apt 安裝，容器重建後消失（待辦 4）。
- `builds.dotnet.microsoft.com` 被網路代理擋住，`dotnet-install.sh` 不可用。
- Dashboard 範本（`dotnet new blazor`）存在，但尚未實際建置驗證。
- 開發分支依 session 指定為 `claude/cool-cerf-xsrphb`；你提供的 Git 規則原文寫的是 `claude/trusting-hopper-wk15uy`，我已改成本 repo 的分支，請確認。

## 想法

- 種植園牌堆預先洗好存入狀態；MCTS 階段用 determinization 重洗未翻開牌。
- Mayor 放置用「逐一放置＋正規化」避免動作空間爆炸。
- 引擎只有單一合法動作時自動套用（設定可關）。
- 結果檔過大時，`games` 另寫 JSONL，主檔只放 summary。
- 單局回放（開事件記錄）供 Dashboard 檢視。
