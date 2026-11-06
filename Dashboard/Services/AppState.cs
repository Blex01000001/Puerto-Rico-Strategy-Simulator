using System.Text.Json;
using PuertoRico.Engine.Simulation;

namespace Dashboard.Services;

/// <summary>Per-browser-session state: the result (or sweep) currently shown.</summary>
public sealed class AppState
{
    public SimulationResult? Result { get; private set; }
    public ResultAnalysis? Analysis { get; private set; }
    public SweepResult? Sweep { get; private set; }
    public string? Source { get; private set; }
    public string? Error { get; private set; }
    public bool Loading { get; private set; }

    public event Action? Changed;

    /// <summary>Folder scanned for result files; default <c>results/</c> next to the solution file.</summary>
    public static string ResultsDirectory(IConfiguration config)
    {
        string? configured = config["Dashboard:ResultsDirectory"];
        if (!string.IsNullOrWhiteSpace(configured)) return Path.GetFullPath(configured);
        string? dir = AppContext.BaseDirectory;
        while (dir != null && !File.Exists(Path.Combine(dir, "PuertoRico.sln"))) dir = Path.GetDirectoryName(dir);
        return Path.Combine(dir ?? Directory.GetCurrentDirectory(), "results");
    }

    public async Task LoadPathAsync(string path)
    {
        if (!File.Exists(path)) { Fail($"找不到檔案：{path}"); return; }
        await using var fs = File.OpenRead(path);
        await LoadStreamAsync(fs, Path.GetFileName(path));
    }

    public async Task LoadStreamAsync(Stream stream, string name)
    {
        Loading = true; Error = null; Changed?.Invoke();
        try
        {
            using var ms = new MemoryStream();
            await stream.CopyToAsync(ms);
            ms.Position = 0;
            bool isSweep;
            using (var doc = await JsonDocument.ParseAsync(ms))
                isSweep = doc.RootElement.ValueKind == JsonValueKind.Object &&
                          doc.RootElement.EnumerateObject().Any(p => string.Equals(p.Name, "points", StringComparison.OrdinalIgnoreCase));
            ms.Position = 0;
            if (isSweep)
            {
                Sweep = await JsonSerializer.DeserializeAsync<SweepResult>(ms, SimulationConfig.JsonOptions)
                        ?? throw new InvalidDataException("空的掃描結果檔");
                Result = null; Analysis = null;
            }
            else
            {
                var result = await JsonSerializer.DeserializeAsync<SimulationResult>(ms, SimulationConfig.JsonOptions)
                             ?? throw new InvalidDataException("空的結果檔");
                if (result.Config.Seats.Count == 0) throw new InvalidDataException("這不是模擬結果檔（沒有 config.seats）");
                Analysis = await Task.Run(() => ResultAnalysis.From(result));
                Result = result; Sweep = null;
            }
            Source = name;
        }
        catch (Exception e) when (e is JsonException or InvalidDataException or IOException)
        {
            Fail($"無法讀取 {name}：{e.Message}");
            return;
        }
        Loading = false;
        Changed?.Invoke();
    }

    private void Fail(string message)
    {
        Error = message; Loading = false;
        Changed?.Invoke();
    }
}
