# TODO — 目前狀態

記錄專案目前的待辦、已知問題與想法。標記：【直接做】使用者點名就能動手；【先討論】會改架構／輸出格式／引入新工具或方向未定；【使用者】需使用者自己操作。維護規則見 `CLAUDE.md`。

## 待辦

1. 【直接做】後續實作依序：靜態表＋GameState＋Clone → Setup → 決策流程骨架 → 各職業（Settler→Builder→Craftsman→Trader→Captain→Mayor→Prospector）→ 終局計分 → 隨機玩家＋單局執行器 → 批次模擬（Parallel.For／checkpoint／Ctrl+C／`--resume`）→ Runner CLI 與結果 JSON → 效能基準。每步驗收標準見對話規劃第八節。

## 已知問題／限制

- 引擎尚未實作，目前只有專案骨架與 1 個煙霧測試；沒有 lint 工具（`dotnet format --verify-no-changes` 可用）。
- SessionStart hook 只有合併到預設分支後，新 session 才會自動套用；hook 的「dotnet 不存在時 apt 安裝」分支在已安裝的容器中無法重測。
- `builds.dotnet.microsoft.com` 被網路代理擋住，`dotnet-install.sh` 不可用。
- Dashboard 尚未建立（第一階段不做）。Dashboard 範本（`dotnet new blazor`）存在，但尚未實際建置驗證。
- 開發分支依 session 指定為 `claude/cool-cerf-xsrphb`；你提供的 Git 規則原文寫的是 `claude/trusting-hopper-wk15uy`，我已改成本 repo 的分支，請確認。

## 想法

- 種植園牌堆預先洗好存入狀態；牌疊用完要洗棄牌堆，所以 GameState 需帶可複製的亂數狀態（如 64 位元計數器）讓洗牌可重現；MCTS 階段用 determinization 重洗未翻開牌。
- Mayor 放置用「逐一放置＋正規化」避免動作空間爆炸。
- 引擎只有單一合法動作時自動套用（設定可關）。
- 結果檔過大時，`games` 另寫 JSONL，主檔只放 summary。
- 單局回放（開事件記錄）供 Dashboard 檢視。
