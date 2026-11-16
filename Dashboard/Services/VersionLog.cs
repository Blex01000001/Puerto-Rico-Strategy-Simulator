using System.Text.Json;

namespace Dashboard.Services;

/// <summary>
/// The version control list (docs/versions.json): one track per version number (rules revision, engine version, feature
/// version, dump format version) with what changed in each version. Shared with the ML UI; Tests/VersionTests.cs checks that
/// its newest entries equal the numbers in the code.
/// </summary>
public static class VersionLog
{
    public sealed record Entry(string Version, string Date, string Commit, IReadOnlyList<string> Changes);

    /// <param name="Display">Pattern for showing a version, e.g. <c>base-v{version}</c>.</param>
    public sealed record Track(string Id, string Title, string Source, string Display, string Meaning, string Bump, IReadOnlyList<Entry> Entries)
    {
        public string Show(string version) => Display.Replace("{version}", version);
        public Entry? Current => Entries.Count > 0 ? Entries[0] : null;
    }

    public static string FilePath() => Path.Combine(AppState.RepoRoot(), "docs", "versions.json");

    /// <summary>Tracks in file order, then one per strategy (id <c>strategy:&lt;name&gt;</c>); empty with an error text when the file is missing or unreadable.</summary>
    public static (List<Track> Tracks, string? Error) Load()
    {
        string path = FilePath();
        if (!File.Exists(path)) return (new(), $"找不到 {AppState.DisplayPath(path)}");
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var tracks = new List<Track>();
            foreach (var t in doc.RootElement.GetProperty("tracks").EnumerateArray())
            {
                tracks.Add(new Track(Str(t, "id"), Str(t, "title"), Str(t, "source"), Str(t, "display"), Str(t, "meaning"), Str(t, "bump"), Entries(t)));
            }
            var info = doc.RootElement.TryGetProperty("strategyTrack", out var st) ? st : default;
            foreach (var t in doc.RootElement.TryGetProperty("strategies", out var list) ? list.EnumerateArray() : default(JsonElement.ArrayEnumerator))
            {
                string id = Str(t, "id");
                tracks.Add(new Track("strategy:" + id, id, "Engine/Strategies/StrategyRegistry.cs：Revisions", id + "-v{version}",
                    info.ValueKind == JsonValueKind.Object ? Str(info, "meaning") : "", info.ValueKind == JsonValueKind.Object ? Str(info, "bump") : "", Entries(t)));
            }
            return (tracks, null);
        }
        catch (Exception e) when (e is JsonException or IOException or KeyNotFoundException or InvalidOperationException)
        {
            return (new(), $"讀不了 {AppState.DisplayPath(path)}：{e.Message}");
        }
    }

    private static List<Entry> Entries(JsonElement track) => track.GetProperty("entries").EnumerateArray().Select(e => new Entry(
        Str(e, "version"), Str(e, "date"), Str(e, "commit"), e.GetProperty("changes").EnumerateArray().Select(c => c.GetString() ?? "").ToList())).ToList();

    private static string Str(JsonElement e, string name) => e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
}
