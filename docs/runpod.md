# 在 RunPod 上跑（產生資料、訓練、對戰）

整個專案都能在 Linux 上獨立執行：Runner（模擬、產生資料、對戰）、ML UI（Python）、Dashboard。RunPod 適合「要跑好幾個小時」的工作（自我對戰、上千局的對戰、大量參數掃描）。腳本在 `deploy/runpod/`。

> 這份說明與腳本在 Ubuntu 24.04 容器裡驗證過（安裝、建置、測試、啟動／停止 UI、只綁 localhost）；**還沒在真正的 RunPod pod 上跑過**，第一次用時請照著做並回報哪裡不同。

## 1. 開哪種 pod

| 要做的事 | 建議 | 原因 |
|---|---|---|
| 產生資料（自我對戰）、對戰驗證、參數掃描 | **CPU pod，核心越多越好**（16～32 核） | 全部是 C# 在 CPU 上跑，時間約與核心數成反比；GPU 完全用不到 |
| LightGBM 訓練 | 同上（CPU） | LightGBM 用 CPU；300 萬列約 4～10 分鐘 |
| MLP 訓練（PyTorch） | 只有資料很大或要試很多組參數時才值得開 GPU pod | 目前 256-128 的網路在 CPU 上一個 epoch 幾分鐘；最後判斷模型仍要跑對戰（CPU） |

- **記憶體**：LightGBM 訓練 300 萬列約需 10 GB，建議 16 GB 以上；之後資料更多時按比例增加。
- **映像**：一般的 Ubuntu 22.04／24.04 映像即可（`setup.sh` 會裝 .NET 8 與 Python 套件）。RunPod 的 PyTorch 映像也可以（已有 PyTorch 與 CUDA）。
- **磁碟**：一定要掛 **volume 在 `/workspace`**，專案放在裡面。pod 停止時 `/workspace` 以外的東西都會消失。訓練資料約 870 bytes／列（4 人局 1 萬局自我對戰約 100 MB），建議 30 GB 以上。
- **SSH**：在 RunPod 設定裡加入你的 SSH 公鑰，pod 開啟「SSH over exposed TCP」，記下 IP 與連接埠（pod 頁面的 Connect 會顯示）。

## 2. 第一次設定

在 pod 的終端機（RunPod 網頁的 Web Terminal 或 SSH）：

```bash
cd /workspace
git clone https://github.com/Blex01000001/puerto-rico-strategy-simulator.git
cd puerto-rico-strategy-simulator
bash deploy/runpod/setup.sh --test
```

- repo 是私人的：clone 時用 GitHub 的 personal access token（只給這個 repo 的 Contents 讀寫權限），例如 `git clone https://<token>@github.com/...`；或在 pod 上 `gh auth login`。**token 不要寫進任何檔案或 commit。**
- `setup.sh` 可以重複執行（`git pull` 之後、或 pod 重開之後再跑一次）：已裝好的會略過。它做的事：裝 .NET 8 SDK（apt，不行就用 Microsoft 的 `dotnet-install.sh` 裝到 `~/.dotnet`）、`python3 -m pip install -r ml/requirements.txt`、建置、把 Runner 發佈到 `publish/runner`；`--test` 再跑 C# 與 Python 測試；`--torch` 在沒有 PyTorch 時安裝。最後會印出核心數、記憶體、磁碟、GPU，以及專案是否在 `/workspace`。
- 如果 `dotnet` 是裝在 `~/.dotnet`，新開的終端機要 `source ~/.bashrc` 才找得到。

## 3. 開 ML UI 與 Dashboard（SSH 通道）

在 pod 上：

```bash
bash deploy/runpod/start.sh
```

兩個都在背景執行、只綁 pod 的 localhost（不對外開放；兩者都沒有登入機制，**不要**用 RunPod 的 HTTP 連接埠直接公開）。`start.sh status` 看狀態、`start.sh stop` 停止；紀錄在 `results/logs/`。

在**你的電腦**上開通道（Windows 10 以上的 PowerShell 也有 `ssh`）：

```bash
ssh -N -L 8501:localhost:8501 -L 5080:localhost:5080 root@<pod IP> -p <SSH 連接埠> -i ~/.ssh/<你的私鑰>
```

然後瀏覽器開 `http://localhost:8501`（ML UI）、`http://localhost:5080`（Dashboard）。通道視窗開著就能用；關掉通道不會影響 pod 上的程式。如果你自己電腦上也開著 Dashboard（佔用 5080），把左邊的數字改掉，例如 `-L 15080:localhost:5080` 再開 `http://localhost:15080`。

## 4. 跑長時間的工作

**用 ML UI**（建議）：「資料」「訓練」「對戰驗證」頁開始的工作都是獨立的背景程序，關掉瀏覽器、關掉 SSH 通道、甚至 `start.sh stop` 都不會中斷；重開後在「工作」頁看進度。

**用命令列**：一定要讓工作脫離 SSH 連線，否則斷線就停：

```bash
setsid nohup dotnet publish/runner/Runner.dll --config ml/data-configs/4p-selfplay-v2.json --dump-positions results/ml/4p-selfplay-v3.bin --dump-rate 0.05 > results/ml/selfplay-v3.log 2>&1 &
```

```bash
tail -c 300 results/ml/selfplay-v3.log
```

（有 `tmux` 的話也可以在 tmux 裡跑。）

- Runner 預設用全部核心（設定檔 `parallelism.maxDegree: 0`）；LightGBM `--threads 0` 也是。兩個重的工作同時跑只會互相搶核心，總時間不會比較短。
- 改了 C# 程式之後，ML UI 的資料／對戰工作會自動重新發佈 Runner；命令列用 `publish/runner` 時要自己重跑 `setup.sh`（或 `dotnet publish Runner -c Release -o publish/runner`）。**有工作正在用 `publish/runner` 時不要重新發佈**（會覆寫執行中的程式）。

## 5. 把結果帶回本機

只帶小檔案：模型（每個約 3 MB）、它的 `.meta.json` 與 `.check.txt`、對戰設定（`mcts/value/*.json`）、產生資料的設定（`ml/data-configs/*.json`）。訓練資料（GB 級）留在 pod 的 `/workspace`。

**方法 A：git**（推薦，紀錄完整）：在 pod 上

```bash
git checkout -b runpod-results
```

```bash
git add ml/models ml/data-configs mcts/value && git commit -m "Models and match configs from RunPod"
```

```bash
git push -u origin runpod-results
```

（`results/` 已被 git 忽略，不會誤推大檔。）回到本機 `git fetch` 後合併。

**方法 B：scp**：在本機

```bash
scp -P <SSH 連接埠> "root@<pod IP>:/workspace/puerto-rico-strategy-simulator/ml/models/4p-v4.txt*" ml/models/
```

對戰的結果檔（`results/ml/<名稱>.json`，數 KB）想在本機 Dashboard 看，也用 scp 帶回 `results/ml/`。`.meta.json` 裡的路徑都是相對專案根目錄，帶回來直接能用；本機的 ML UI「模型清單」會顯示 pod 上跑的對戰勝率。

## 6. 費用與中斷

- 不用時 **Stop** pod：`/workspace` 的資料保留（只收儲存費）；**Terminate** 會刪掉 pod（volume 另外保留與否看你建立時的設定）。
- Stop 會直接結束所有程式：ML UI 會把當時的工作標成「中斷」；被中斷的產生資料工作**不會**寫出說明檔（`.bin.json`），那份資料讀不了，要重跑。停 pod 前先在「工作」頁確認沒有在跑的工作，或先按「取消」（取消會保留已完成的局數）。
- 估時間（依核心數線性粗估，未實測）：本機 4 核心約 1 局／秒的自我對戰（100 次模擬、`leafRollout` 20），32 核心約 8 局／秒，8,000 局約 17 分鐘。

## 7. 重現性

- C# 部分（模擬、產生資料、對戰）同一個 commit、同一份設定與種子，在任何機器上結果都完全相同（與執行緒數無關）。
- 模型推論（LightGBM、MLP）在 C# 裡是確定性的：同一個模型檔，對戰結果在 pod 與本機相同。
- 重新**訓練**不一定完全相同：LightGBM 換機器或執行緒數可能有些微差異，GPU 上的 PyTorch 每次都可能不同。判斷看對戰勝率；`.meta.json` 會記錄套件版本與裝置。

## 8. 疑難排解

| 狀況 | 處理 |
|---|---|
| `dotnet: command not found`（裝在 `~/.dotnet`） | `source ~/.bashrc`，或重跑 `setup.sh` |
| ML UI 的資料／對戰工作失敗「找不到 dotnet」 | 用 `start.sh` 啟動 ML UI（它會把 `~/.dotnet` 加進 PATH） |
| 通道連不上 | 確認 pod 的 SSH 連接埠、私鑰路徑；`start.sh status` 看兩個服務有沒有在跑 |
| 本機 8501／5080 已被佔用 | 通道左邊的連接埠換一個（見第 3 節） |
| 訓練被系統停掉（Killed） | 記憶體不夠：開記憶體較大的 pod，或少選幾份資料 |
| 磁碟滿了 | 刪掉不用的 `results/ml/*.bin`（連同 `.bin.json`）；模型與設定都在 git 裡 |
