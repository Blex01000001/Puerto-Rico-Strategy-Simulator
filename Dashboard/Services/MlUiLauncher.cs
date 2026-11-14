using System.Diagnostics;

namespace Dashboard.Services;

/// <summary>
/// Status and start-up of the ML UI (ml/ui.py, a separate Python/Streamlit program on localhost:8501).
/// The Dashboard does not depend on it: it only checks whether the port answers and, on request, runs the project's own
/// start script (ml/start-ui.cmd in a new console window on Windows, ml/start-ui.sh in the background elsewhere).
/// The started ML UI is independent of the Dashboard (closing the Dashboard does not stop it). Nothing typed by the user
/// reaches the command line: the script path is fixed.
/// </summary>
public static class MlUiLauncher
{
    public const string Url = "http://localhost:8501";
    public const string InstallHint = "新裝置第一次使用前，先在專案根目錄執行一次：python -m pip install -r ml/requirements.txt";
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(1) };

    /// <summary>True when the ML UI answers its health check.</summary>
    public static async Task<bool> IsRunningAsync(CancellationToken cancel = default)
    {
        try
        {
            using var response = await Http.GetAsync(Url + "/_stcore/health", cancel);
            return response.IsSuccessStatusCode;
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or OperationCanceledException)
        {
            return false;
        }
    }

    /// <summary>
    /// Checks Python and the packages, runs the start script and waits until the ML UI answers.
    /// Returns null on success, otherwise a message for the user (in Traditional Chinese).
    /// </summary>
    public static async Task<string?> StartAsync(CancellationToken cancel = default)
    {
        if (await IsRunningAsync(cancel)) return null;
        string root = AppState.RepoRoot();
        bool windows = OperatingSystem.IsWindows();
        string script = Path.Combine(root, "ml", windows ? "start-ui.cmd" : "start-ui.sh");
        if (!File.Exists(script)) return $"找不到啟動檔 {AppState.DisplayPath(script)}。";

        string? missing = await CheckPythonAsync(windows, cancel);
        if (missing != null) return missing;

        try
        {
            if (windows)
            {
                // a console window of its own, like double-clicking the script; it keeps running after the Dashboard stops
                Process.Start(new ProcessStartInfo(script, "--server.headless true") { UseShellExecute = true, WorkingDirectory = root });
            }
            else
            {
                string logDir = Path.Combine(root, "results", "logs");
                Directory.CreateDirectory(logDir);
                string log = Path.Combine(logDir, "ml-ui.log");
                var psi = new ProcessStartInfo("/bin/sh") { UseShellExecute = false, WorkingDirectory = root };
                psi.ArgumentList.Add("-c");
                psi.ArgumentList.Add("setsid nohup \"$0\" --server.headless true > \"$1\" 2>&1 < /dev/null &");
                psi.ArgumentList.Add(script);
                psi.ArgumentList.Add(log);
                using var p = Process.Start(psi);
                p?.WaitForExit(5000);
            }
        }
        catch (Exception e) when (e is System.ComponentModel.Win32Exception or InvalidOperationException or IOException)
        {
            return $"無法執行啟動檔：{AppState.Scrub(e.Message)}";
        }

        for (int i = 0; i < 60; i++)
        {
            await Task.Delay(1000, cancel);
            if (await IsRunningAsync(cancel)) return null;
        }
        return windows
            ? "ML UI 在 60 秒內沒有回應：請看剛剛跳出的 cmd 視窗裡的錯誤訊息。"
            : "ML UI 在 60 秒內沒有回應：請看 results/logs/ml-ui.log。";
    }

    /// <summary>
    /// Null when a Python with the ML UI's packages is found, tried in the same order as the start scripts
    /// (PR_PYTHON first, then python and py on Windows, python3 and python elsewhere). Otherwise the message of
    /// ml/check_env.py for the first Python found: it names that interpreter and the exact pip command for it.
    /// </summary>
    private static async Task<string?> CheckPythonAsync(bool windows, CancellationToken cancel)
    {
        string root = AppState.RepoRoot();
        string check = Path.Combine(root, "ml", "check_env.py");
        var candidates = new List<string>();
        string? forced = Environment.GetEnvironmentVariable("PR_PYTHON");
        if (!string.IsNullOrWhiteSpace(forced)) candidates.Add(forced);
        else candidates.AddRange(windows ? new[] { "python", "py" } : new[] { "python3", "python" });

        string? firstReport = null;
        foreach (var exe in candidates)
        {
            var psi = new ProcessStartInfo(exe) { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true, WorkingDirectory = root };
            psi.ArgumentList.Add(check);
            psi.Environment["PYTHONIOENCODING"] = "utf-8"; // the report contains Chinese text
            try
            {
                using var p = Process.Start(psi);
                if (p == null) continue;
                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancel);
                timeout.CancelAfter(TimeSpan.FromSeconds(30));
                string output = await p.StandardOutput.ReadToEndAsync(timeout.Token);
                await p.WaitForExitAsync(timeout.Token);
                if (p.ExitCode == 0) return null;
                firstReport ??= output.Trim();
            }
            catch (System.ComponentModel.Win32Exception)
            {
                // this name is not installed; try the next one
            }
            catch (OperationCanceledException)
            {
                return "檢查 Python 套件逾時（30 秒）。";
            }
        }
        if (firstReport == null)
            return "找不到 Python：請先安裝 Python 3（安裝時勾選 Add to PATH），然後在專案根目錄執行：python -m pip install -r ml/requirements.txt";
        if (string.IsNullOrEmpty(firstReport)) return "缺少 ML UI 需要的 Python 套件。" + InstallHint;
        // the project path is shown relative to the root (Dashboard rule); the Python path stays: it is the point of the message
        return AppState.Scrub(firstReport) + "\n（在專案根目錄執行；裝好後再按一次「ML UI」）";
    }
}
