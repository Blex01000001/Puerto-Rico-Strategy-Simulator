using System.Text.Json;

namespace Dashboard.Services;

/// <summary>
/// UI texts looked up by key from the shared i18n folder (<c>i18n/dash.&lt;lang&gt;.json</c>; the ML UI reads its own <c>ml.&lt;lang&gt;.json</c>
/// there). English is the default and the fallback; a key missing everywhere shows the key itself. Placeholders are
/// positional ({0}, {1}) and are filled by <see cref="T"/>. One instance per browser session: <see cref="Use"/> sets its language
/// from the <c>pr-lang</c> cookie (App.razor), the sidebar button switches it through <c>/lang/{code}</c>.
/// </summary>
public sealed class Loc
{
    public const string Cookie = "pr-lang";
    public const string Default = "en";
    public static readonly string[] Languages = { "en", "zh-TW" };

    private static readonly Lazy<Dictionary<string, Dictionary<string, string>>> Tables = new(() =>
        Languages.ToDictionary(l => l, Load));

    public string Lang { get; private set; } = Choose(null);
    public string Other => Lang == "en" ? "zh-TW" : "en";
    public bool Chinese => Lang == "zh-TW";

    /// <summary>Picks a supported language: the given (cookie) value, then the PR_LANG environment variable, then English.</summary>
    public static string Choose(string? value)
    {
        foreach (var candidate in new[] { value, Environment.GetEnvironmentVariable("PR_LANG") })
            if (candidate != null && Languages.Contains(candidate)) return candidate;
        return Default;
    }

    public void Use(string? value) => Lang = Choose(value);

    public string T(string key, params object?[] args)
    {
        string text = Tables.Value[Lang].TryGetValue(key, out var own) ? own
            : Tables.Value[Default].TryGetValue(key, out var fallback) ? fallback : key;
        return args.Length == 0 ? text : string.Format(text, args);
    }

    /// <summary>The message of an exception in this language: a <see cref="LocException"/> is looked up by key, anything else keeps its own text.</summary>
    public string Describe(Exception e) => e is LocException le ? T(le.Key, le.Args) : e.Message;

    /// <summary>End-of-game reason(s) of a game record ("a+b" = several at once).</summary>
    public string EndReason(string? key) =>
        string.IsNullOrEmpty(key) ? T("reason.none") : string.Join(T("reason.sep"), key.Split('+').Select(k => Has("reason." + k) ? T("reason." + k) : k));

    public bool Has(string key) => Tables.Value[Lang].ContainsKey(key) || Tables.Value[Default].ContainsKey(key);

    /// <summary>All keys of a language (for the consistency check of the i18n files).</summary>
    public static IReadOnlyDictionary<string, string> Table(string lang) => Tables.Value[lang];

    private static Dictionary<string, string> Load(string lang)
    {
        string path = Path.Combine(AppState.RepoRoot(), "i18n", $"dash.{lang}.json");
        return File.Exists(path)
            ? JsonSerializer.Deserialize<Dictionary<string, string>>(File.ReadAllText(path)) ?? new()
            : new();
    }
}

/// <summary>A data error (bad or missing file) whose text is looked up by key when it is shown (see <see cref="Loc.Describe"/>); the key is its fallback message.</summary>
public sealed class LocException : Exception
{
    public string Key { get; }
    public object?[] Args { get; }
    public LocException(string key, params object?[] args) : base(key) { Key = key; Args = args; }
}
