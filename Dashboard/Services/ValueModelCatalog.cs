using System.Globalization;
using System.Text.Json;

namespace Dashboard.Services;

/// <summary>
/// Value models in <c>ml/models/</c> (trained by the ML UI / ml/*.py) for the MCTS <c>valueModel</c> dropdown.
/// Only reads files: the model itself and its optional <c>.meta.json</c> (player count, kind, best win share against the
/// original MCTS). The Dashboard does not depend on Python or on the ML UI running.
/// </summary>
public static class ValueModelCatalog
{
    /// <param name="Path">Path as written into the config, relative to the project root with forward slashes (e.g. <c>ml/models/4p-v2.txt</c>).</param>
    /// <param name="Players">From the metadata; null when unknown (no <c>.meta.json</c>).</param>
    public sealed record Entry(string Path, string Name, string Kind, int? Players, double? BestWinVsDefault)
    {
        public string Label
        {
            get
            {
                var parts = new List<string> { Kind };
                if (Players is { } p) parts.Add($"{p} 人局");
                if (BestWinVsDefault is { } w) parts.Add($"對原版 MCTS {(w * 100).ToString("0.0", CultureInfo.InvariantCulture)}%");
                return $"{Name}（{string.Join("，", parts)}）";
            }
        }
    }

    public static string ModelsDirectory() => System.IO.Path.Combine(AppState.RepoRoot(), "ml", "models");

    /// <summary>Models usable for <paramref name="players"/> (models without metadata are listed too: their player count is unknown).</summary>
    public static List<Entry> List(int players)
    {
        var dir = ModelsDirectory();
        if (!Directory.Exists(dir)) return new();
        var list = new List<Entry>();
        foreach (var file in Directory.EnumerateFiles(dir).OrderBy(f => f, StringComparer.Ordinal))
        {
            string name = System.IO.Path.GetFileName(file);
            if (name.EndsWith(".meta.json", StringComparison.Ordinal) || name.EndsWith(".check.txt", StringComparison.Ordinal)) continue;
            bool lgbm = name.EndsWith(".txt", StringComparison.Ordinal);
            if (!lgbm && !name.EndsWith(".json", StringComparison.Ordinal)) continue;
            var entry = new Entry($"ml/models/{name}", name, lgbm ? "LightGBM" : "MLP", null, null);
            entry = WithMeta(entry, file + ".meta.json");
            if (entry.Players is null || entry.Players == players) list.Add(entry);
        }
        return list;
    }

    private static Entry WithMeta(Entry entry, string metaPath)
    {
        if (!File.Exists(metaPath)) return entry;
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(metaPath));
            var root = doc.RootElement;
            int? players = root.TryGetProperty("players", out var p) && p.ValueKind == JsonValueKind.Number ? p.GetInt32() : null;
            double? best = null;
            if (root.TryGetProperty("matches", out var matches) && matches.ValueKind == JsonValueKind.Array)
            {
                foreach (var m in matches.EnumerateArray())
                {
                    bool vsDefault = m.TryGetProperty("others", out var others) && others.EnumerateArray().Any(o =>
                        o.TryGetProperty("strategy", out var s) && s.GetString() == "mcts" &&
                        (!o.TryGetProperty("valueModel", out var vm) || vm.ValueKind == JsonValueKind.Null));
                    if (vsDefault && m.TryGetProperty("winShare", out var w) && w.ValueKind == JsonValueKind.Number)
                        best = Math.Max(best ?? 0, w.GetDouble());
                }
            }
            return entry with { Players = players, BestWinVsDefault = best };
        }
        catch (Exception e) when (e is JsonException or IOException or InvalidOperationException)
        {
            return entry; // unreadable metadata: still offer the model
        }
    }
}
