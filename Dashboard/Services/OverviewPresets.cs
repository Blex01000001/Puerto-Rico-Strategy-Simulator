using System.Text.Json;

namespace Dashboard.Services;

/// <summary>
/// Named sets of result files for the overview page ("preset combinations"). Stored as file names (not paths) in
/// <c>.presets/overview-presets.json</c> inside the results folder; the sub-folder keeps it out of every file list.
/// </summary>
public static class OverviewPresets
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };

    private static string FilePath(string resultsDir) => Path.Combine(resultsDir, ".presets", "overview-presets.json");

    public static Dictionary<string, List<string>> Load(string resultsDir)
    {
        try
        {
            string path = FilePath(resultsDir);
            if (!File.Exists(path)) return new();
            return JsonSerializer.Deserialize<Dictionary<string, List<string>>>(File.ReadAllText(path)) ?? new();
        }
        catch (Exception e) when (e is JsonException or IOException) { return new(); }
    }

    /// <summary>Saves (or replaces) a preset; the stored names are file names without folder.</summary>
    public static void Save(string resultsDir, string name, IEnumerable<string> files)
    {
        var all = Load(resultsDir);
        all[name] = files.Select(Path.GetFileName).Where(n => !string.IsNullOrEmpty(n)).Select(n => n!).Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(n => n, StringComparer.OrdinalIgnoreCase).ToList();
        Write(resultsDir, all);
    }

    public static void Delete(string resultsDir, string name)
    {
        var all = Load(resultsDir);
        if (all.Remove(name)) Write(resultsDir, all);
    }

    private static void Write(string resultsDir, Dictionary<string, List<string>> all)
    {
        string path = FilePath(resultsDir);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string tmp = path + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(all, Json));
        File.Move(tmp, path, overwrite: true);
    }
}
