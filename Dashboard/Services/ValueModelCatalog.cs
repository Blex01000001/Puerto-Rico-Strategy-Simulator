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
    /// <param name="Local">True for the local workspace (ml/local/models, not in git), false for official models (ml/models).</param>
    public sealed record Entry(string Path, string Name, string Kind, int? Players, double? BestWinVsDefault, bool Local = false)
    {
        /// <summary>Dropdown text: name and (official / local, kind, player count, best win share against the original MCTS).</summary>
        public string Label(Loc l)
        {
            var parts = new List<string> { l.T(Local ? "model.label.local" : "model.label.official"), Kind };
            if (Players is { } p) parts.Add(l.T("model.label.players", p));
            if (BestWinVsDefault is { } w) parts.Add(l.T("model.label.best", (w * 100).ToString("0.0", CultureInfo.InvariantCulture)));
            return $"{Name} ({string.Join(l.T("model.label.sep"), parts)})";
        }
    }

    public static string ModelsDirectory() => System.IO.Path.Combine(AppState.RepoRoot(), "ml", "models");
    /// <summary>The ML UI's local workspace (ignored by git): models trained on this machine and the match results of official models.</summary>
    public static string LocalDirectory() => System.IO.Path.Combine(AppState.RepoRoot(), "ml", "local");

    /// <summary>Models usable for <paramref name="players"/> (models without metadata are listed too: their player count is unknown).</summary>
    /// <summary>Models usable for <paramref name="players"/>: official first, then local (models without metadata are listed too:
    /// their player count is unknown).</summary>
    public static List<Entry> List(int players)
    {
        var list = new List<Entry>();
        Add(list, ModelsDirectory(), "ml/models", local: false, players);
        Add(list, System.IO.Path.Combine(LocalDirectory(), "models"), "ml/local/models", local: true, players);
        return list;
    }

    private static void Add(List<Entry> list, string dir, string relDir, bool local, int players)
    {
        if (!Directory.Exists(dir)) return;
        foreach (var file in Directory.EnumerateFiles(dir).OrderBy(f => f, StringComparer.Ordinal))
        {
            string name = System.IO.Path.GetFileName(file);
            if (name.EndsWith(".meta.json", StringComparison.Ordinal) || name.EndsWith(".check.txt", StringComparison.Ordinal)) continue;
            bool lgbm = name.EndsWith(".txt", StringComparison.Ordinal);
            if (!lgbm && !name.EndsWith(".json", StringComparison.Ordinal)) continue;
            var entry = new Entry($"{relDir}/{name}", name, lgbm ? "LightGBM" : "MLP", null, null, local);
            entry = WithMeta(entry, file + ".meta.json");
            // official models: matches run on this machine are kept in ml/local/match-records (the tracked meta stays untouched)
            if (!local) entry = WithMatches(entry, System.IO.Path.Combine(LocalDirectory(), "match-records", name + ".matches.json"));
            if (entry.Players is null || entry.Players == players) list.Add(entry);
        }
    }

    private static Entry WithMatches(Entry entry, string recordsPath)
    {
        if (!File.Exists(recordsPath)) return entry;
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(recordsPath));
            double? best = BestVsDefault(doc.RootElement);
            return best is { } b && (entry.BestWinVsDefault is null || b > entry.BestWinVsDefault) ? entry with { BestWinVsDefault = b } : entry;
        }
        catch (Exception e) when (e is JsonException or IOException or InvalidOperationException)
        {
            return entry;
        }
    }

    private static Entry WithMeta(Entry entry, string metaPath)
    {
        if (!File.Exists(metaPath)) return entry;
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(metaPath));
            var root = doc.RootElement;
            int? players = root.TryGetProperty("players", out var p) && p.ValueKind == JsonValueKind.Number ? p.GetInt32() : null;
            double? best = root.TryGetProperty("matches", out var matches) ? BestVsDefault(matches) : null;
            return entry with { Players = players, BestWinVsDefault = best };
        }
        catch (Exception e) when (e is JsonException or IOException or InvalidOperationException)
        {
            return entry; // unreadable metadata: still offer the model
        }
    }

    /// <summary>Highest win share among matches that had the original MCTS (no value model) at the table.</summary>
    private static double? BestVsDefault(JsonElement matches)
    {
        if (matches.ValueKind != JsonValueKind.Array) return null;
        double? best = null;
        foreach (var m in matches.EnumerateArray())
        {
            bool vsDefault = m.TryGetProperty("others", out var others) && others.EnumerateArray().Any(o =>
                o.TryGetProperty("strategy", out var s) && s.GetString() == "mcts" &&
                (!o.TryGetProperty("valueModel", out var vm) || vm.ValueKind == JsonValueKind.Null));
            if (vsDefault && m.TryGetProperty("winShare", out var w) && w.ValueKind == JsonValueKind.Number)
                best = Math.Max(best ?? 0, w.GetDouble());
        }
        return best;
    }
}
