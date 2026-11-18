namespace PuertoRico.Engine.Simulation;

/// <summary>
/// Which files the Dashboard's pickers offer as result files: <c>results/*.json</c> and the ML UI's <c>results/ml/*.json</c>
/// (the match results it writes there). Other sub-folders (<c>ml/jobs/</c>, <c>.presets/</c>) are not scanned, and dump metadata
/// (<c>*.bin.json</c>) is not a result. UI-free so it is testable.
/// </summary>
public static class ResultFiles
{
    /// <summary>The sub-folder the ML UI writes its match results to.</summary>
    public const string MlFolder = "ml";

    public static List<string> List(string dir)
    {
        var files = new List<string>();
        if (!Directory.Exists(dir)) return files;
        files.AddRange(Directory.GetFiles(dir, "*.json"));
        string ml = Path.Combine(dir, MlFolder);
        if (Directory.Exists(ml)) files.AddRange(Directory.GetFiles(ml, "*.json"));
        return files.Where(f => !f.EndsWith(".tmp", StringComparison.OrdinalIgnoreCase) && !f.EndsWith(".bin.json", StringComparison.OrdinalIgnoreCase))
                    .OrderBy(f => f, StringComparer.OrdinalIgnoreCase).ToList();
    }

    /// <summary>The name shown in a picker: the file name, with its folder ("ml/x.json") when it is not directly in <paramref name="dir"/>.</summary>
    public static string Label(string dir, string path) => Path.GetRelativePath(dir, path).Replace('\\', '/');
}
