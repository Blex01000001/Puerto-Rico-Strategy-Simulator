using System.Text.Json;
using PuertoRico.Engine.Simulation;

namespace Dashboard.Services;

/// <summary>Per-browser-session state: the result (or sweep) currently shown.</summary>
public sealed class AppState
{
    private readonly Loc _loc;
    public AppState(Loc loc) { _loc = loc; }

    public SimulationResult? Result { get; private set; }
    public ResultAnalysis? Analysis { get; private set; }
    public SweepResult? Sweep { get; private set; }
    public string? Source { get; private set; }
    public string? Error { get; private set; }
    public bool Loading { get; private set; }

    public event Action? Changed;

    /// <summary>A configuration handed to the simulate page ("simulate again with this setup"); consumed once.</summary>
    public SimulationConfig? Template { get; private set; }
    public string? TemplateSource { get; private set; }

    public void SetTemplate(SimulationConfig config, string source)
    {
        Template = SimulationConfig.Clone(config);
        TemplateSource = source;
    }

    public (SimulationConfig Config, string Source)? TakeTemplate()
    {
        if (Template == null) return null;
        var t = (Template, TemplateSource ?? "");
        Template = null; TemplateSource = null;
        return t;
    }

    private static readonly System.Collections.Concurrent.ConcurrentDictionary<(string Path, long Length, long Ticks), SimulationConfig> ConfigCache = new();

    /// <summary>
    /// Reads only the <c>config</c> section of a result or sweep file. The config is among the first properties of the file, so only the
    /// beginning is read (64 KB, doubled until the config is complete): a folder of big result files lists in moments and nothing is
    /// held in memory. The answer is cached per file (path, size, modification time).
    /// </summary>
    public static async Task<SimulationConfig> ReadConfigAsync(string path)
    {
        if (!File.Exists(path)) throw new LocException("err.not_found", DisplayPath(path));
        var info = new FileInfo(path);
        var key = (path, info.Length, info.LastWriteTimeUtc.Ticks);
        if (ConfigCache.TryGetValue(key, out var cached)) return SimulationConfig.Clone(cached);
        await using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite, 4096, useAsync: true);
        long size = Math.Min(64 * 1024, fs.Length);
        while (true)
        {
            var bytes = new byte[size];
            fs.Position = 0;
            int read = 0;
            while (read < size) { int n = await fs.ReadAsync(bytes.AsMemory(read, (int)size - read)); if (n == 0) break; read += n; }
            bool whole = read >= fs.Length;
            try
            {
                var cfg = ExtractConfig(read == bytes.Length ? bytes : bytes[..read], Path.GetFileName(path));
                if (ConfigCache.Count > 2000) ConfigCache.Clear();
                ConfigCache[key] = SimulationConfig.Clone(cfg);
                return cfg;
            }
            catch (Exception e) when (!whole && (e is JsonException || e is LocException))
            {
                size = Math.Min(size * 4, fs.Length); // the config did not fit in what was read: read more
            }
        }
    }

    private static SimulationConfig ExtractConfig(byte[] bytes, string fileName)
    {
        var reader = new Utf8JsonReader(bytes, new JsonReaderOptions { AllowTrailingCommas = true, CommentHandling = JsonCommentHandling.Skip });
        if (!reader.Read() || reader.TokenType != JsonTokenType.StartObject) throw new LocException("err.not_object");
        while (reader.Read())
        {
            if (reader.TokenType != JsonTokenType.PropertyName) continue;
            bool isConfig = string.Equals(reader.GetString(), "config", StringComparison.OrdinalIgnoreCase);
            reader.Read();
            if (isConfig)
            {
                var cfg = JsonSerializer.Deserialize<SimulationConfig>(ref reader, SimulationConfig.JsonOptions)
                          ?? throw new LocException("err.empty_config");
                if (cfg.Seats.Count == 0) throw new LocException("err.no_seats");
                return cfg;
            }
            reader.Skip();
        }
        throw new LocException("err.no_config", fileName);
    }

    /// <summary>Folder that holds PuertoRico.sln (found upwards from the app), or the current directory.</summary>
    public static string RepoRoot()
    {
        string? dir = AppContext.BaseDirectory;
        while (dir != null && !File.Exists(Path.Combine(dir, "PuertoRico.sln"))) dir = Path.GetDirectoryName(dir);
        return dir ?? Directory.GetCurrentDirectory();
    }

    /// <summary>Path as shown to the user: relative to the project root (e.g. <c>results</c>), never the machine's full path.</summary>
    public static string DisplayPath(string path)
    {
        if (string.IsNullOrWhiteSpace(path)) return path;
        string rel;
        try { rel = Path.GetRelativePath(RepoRoot(), Path.GetFullPath(path)); }
        catch (ArgumentException) { return Path.GetFileName(path); }
        return rel.StartsWith("..", StringComparison.Ordinal) || Path.IsPathRooted(rel) ? Path.GetFileName(path.TrimEnd('/', '\\')) : rel;
    }

    /// <summary>Removes the machine's project root from a message (e.g. an exception text) so no full path is shown.</summary>
    public static string Scrub(string message)
    {
        string root = RepoRoot();
        return message.Replace(root + Path.DirectorySeparatorChar, "").Replace(root, ".");
    }

    public static string ResultsDirectory(IConfiguration config)
    {
        string? configured = config["Dashboard:ResultsDirectory"];
        if (!string.IsNullOrWhiteSpace(configured)) return Path.GetFullPath(configured);
        return Path.Combine(RepoRoot(), "results");
    }

    public async Task LoadPathAsync(string path)
    {
        if (!File.Exists(path)) { Fail(_loc.T("err.not_found", DisplayPath(path))); return; }
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
                        ?? throw new LocException("err.empty_sweep");
                Result = null; Analysis = null;
            }
            else
            {
                var result = await JsonSerializer.DeserializeAsync<SimulationResult>(ms, SimulationConfig.JsonOptions)
                             ?? throw new LocException("err.empty_result");
                if (result.Config.Seats.Count == 0) throw new LocException("err.not_result");
                Analysis = await Task.Run(() => ResultAnalysis.From(result));
                Result = result; Sweep = null;
            }
            Source = name;
        }
        catch (Exception e) when (e is JsonException or InvalidDataException or LocException or IOException)
        {
            Fail(_loc.T("err.cannot_read", name, Scrub(_loc.Describe(e))));
            return;
        }
        Loading = false;
        Changed?.Invoke();
    }

    /// <summary>Read and analyse a result file without touching the shown result (used by the compare page).</summary>
    public static async Task<(SimulationResult Result, ResultAnalysis Analysis)> ReadResultAsync(string path)
    {
        if (!File.Exists(path)) throw new LocException("err.not_found", DisplayPath(path));
        await using var fs = File.OpenRead(path);
        var result = await JsonSerializer.DeserializeAsync<SimulationResult>(fs, SimulationConfig.JsonOptions)
                     ?? throw new LocException("err.empty_result");
        if (result.Config.Seats.Count == 0) throw new LocException("err.not_normal_sweep", Path.GetFileName(path));
        return (result, await Task.Run(() => ResultAnalysis.From(result)));
    }

    /// <summary>Read a result file and keep only its summary (for the overview page; the per-game records are dropped).</summary>
    public static async Task<OverviewTable> ReadOverviewAsync(string path)
    {
        if (!File.Exists(path)) throw new LocException("err.not_found", DisplayPath(path));
        await using var fs = File.OpenRead(path);
        var result = await JsonSerializer.DeserializeAsync<SimulationResult>(fs, SimulationConfig.JsonOptions)
                     ?? throw new LocException("err.empty_result");
        if (result.Config.Seats.Count == 0 || result.Summary.Count == 0)
            throw new LocException("err.not_normal", Path.GetFileName(path));
        var analysis = result.Games.Count > 0 ? await Task.Run(() => ResultAnalysis.From(result)) : null;
        return TournamentOverview.FromResult(Path.GetFileNameWithoutExtension(path), result, analysis);
    }

    private void Fail(string message)
    {
        Error = message; Loading = false;
        Changed?.Invoke();
    }
}
