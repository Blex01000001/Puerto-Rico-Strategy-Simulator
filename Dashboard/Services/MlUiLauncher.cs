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
    /// <summary>
    /// Health check on 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 (::1) first, where Streamlit does not
    /// listen, and a refused connection there takes about 2 s before IPv4 is tried; with a short timeout the check failed
    /// now and then and the status light flickered.
    /// </summary>
    private const string HealthUrl = "http://127.0.0.1:8501/_stcore/health";
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(3) };

    /// <summary>True when the ML UI answers its health check.</summary>
    public static async Task<bool> IsRunningAsync(CancellationToken cancel = default)
    {
        try
        {
            using var response = await Http.GetAsync(HealthUrl, cancel);
            return response.IsSuccessStatusCode;
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or OperationCanceledException)
        {
            return false;
        }
    }

    /// <summary>
    /// Checks Python and the packages, runs the start script and waits until the ML UI answers.
    /// Returns null on success, otherwise a message for the user (in the language of <paramref name="l"/>).
    /// </summary>
    public static async Task<string?> StartAsync(Loc l, CancellationToken cancel = default)
    {
        if (await IsRunningAsync(cancel)) return null;
        string root = AppState.RepoRoot();
        bool windows = OperatingSystem.IsWindows();
        string script = Path.Combine(root, "ml", windows ? "start-ui.cmd" : "start-ui.sh");
        if (!File.Exists(script)) return l.T("ml.err.no_script", AppState.DisplayPath(script));

        string? missing = await CheckPythonAsync(l, windows, cancel);
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
            return l.T("ml.err.run", AppState.Scrub(e.Message));
        }

        for (int i = 0; i < 60; i++)
        {
            await Task.Delay(1000, cancel);
            if (await IsRunningAsync(cancel)) return null;
        }
        return windows
            ? l.T("ml.err.timeout_win")
            : l.T("ml.err.timeout_log");
    }

    /// <summary>
    /// Null when a Python with the ML UI's packages is found, tried in the same order as the start scripts
    /// (PR_PYTHON first, then python and py on Windows, python3 and python elsewhere). Otherwise the message of
    /// ml/check_env.py for the first Python found: it names that interpreter and the exact pip command for it.
    /// </summary>
    private static async Task<string?> CheckPythonAsync(Loc l, bool windows, CancellationToken cancel)
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
            psi.ArgumentList.Add("--lang");
            psi.ArgumentList.Add(l.Lang);
            psi.Environment["PYTHONIOENCODING"] = "utf-8"; // the report may contain Chinese text
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
                return l.T("ml.err.check_timeout");
            }
        }
        if (firstReport == null)
            return l.T("ml.err.no_python");
        if (string.IsNullOrEmpty(firstReport)) return l.T("ml.err.missing") + l.T("ml.install_hint");
        // the project path is shown relative to the root (Dashboard rule); the Python path stays: it is the point of the message
        return AppState.Scrub(firstReport) + l.T("ml.err.rerun");
    }
}
