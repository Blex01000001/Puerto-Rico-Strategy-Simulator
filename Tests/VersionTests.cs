using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies;
using PuertoRico.Engine.Strategies.Mcts;
using Xunit;

namespace PuertoRico.Tests;

/// <summary>
/// Version control (CLAUDE.md, section 版本與 hash).
/// Golden master: fixed games whose hashes are stored in Tests/Data/golden.json. The "rules" cases are random players
/// only (rules, RNG and the random strategy); every other strategy has its own cases (it plus random players), so a failure
/// says WHAT changed. ml/strategy-params.json holds every strategy's revision and resolved default parameters (the ML
/// tools read it); a changed default is reported apart from a changed decision logic.
/// Regenerate both files with PR_UPDATE_GOLDEN=1 dotnet test --filter Golden, only after deciding the versions.
/// </summary>
public class GoldenTests
{
    internal static string RepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "PuertoRico.sln"))) dir = dir.Parent;
        return dir?.FullName ?? throw new InvalidOperationException("PuertoRico.sln not found above " + AppContext.BaseDirectory);
    }

    private static string GoldenPath => Path.Combine(RepoRoot(), "Tests", "Data", "golden.json");
    internal static string ParamsPath => Path.Combine(RepoRoot(), "ml", "strategy-params.json");

    private static readonly JsonSerializerOptions Pretty = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    /// <summary>MCTS is left out: floating-point functions (Math.Log...) may differ in the last digit between platforms.</summary>
    internal static readonly string[] GoldenStrategies = StrategyRegistry.Revisions.Keys
        .Where(n => n != "mcts" && n != "random").OrderBy(n => n, StringComparer.Ordinal).ToArray();

    private static SimulationConfig Cfg(int players, int games, ulong seed, SeatOrderMode order, params string[] strategies) => new()
    {
        Players = players, Games = games, Seed = seed, SeatOrder = order,
        Seats = strategies.Select((s, i) => new SeatConfig { Id = $"s{i}", Strategy = s }).ToList(),
    };

    private static SimulationConfig RulesCase(int players) =>
        Cfg(players, 60, players == 3 ? 7101UL : 7102UL, SeatOrderMode.Random, Enumerable.Repeat("random", players).ToArray());

    private static SimulationConfig StrategyCase(string strategy, int players) =>
        Cfg(players, players == 3 ? 30 : 48, players == 3 ? 7201UL : 7202UL, SeatOrderMode.Balanced,
            new[] { strategy }.Concat(Enumerable.Repeat("random", players - 1)).ToArray());

    /// <summary>
    /// SHA-256 over the behaviour of every game: rounds, decisions, end reason, winners and per player the scores,
    /// buildings, build rounds, tiles, coins and shipments. Written field by field (not the serialized record), so a new
    /// output field does not look like a behaviour change.
    /// </summary>
    internal static string HashOf(SimulationConfig cfg)
    {
        using var sha = SHA256.Create();
        var sb = new StringBuilder();
        for (int g = 0; g < cfg.Games; g++)
        {
            var r = GameRunner.Play(cfg, g);
            sb.Clear();
            sb.Append(r.Index).Append('|').Append(r.Seed).Append('|').Append(r.Rounds).Append('|').Append(r.Decisions).Append('|')
              .Append(r.EndReason).Append('|').Append(string.Join(',', r.Winners));
            foreach (var p in r.Players)
                sb.Append(";").Append(p.Seat).Append(',').Append(p.SeatId).Append(',').Append(p.Vp).Append(',').Append(p.Chips).Append(',')
                  .Append(p.BuildingPoints).Append(',').Append(p.BonusPoints).Append(',').Append(p.Tiebreak).Append(',').Append(p.Rank).Append(',')
                  .Append(string.Join(' ', p.Buildings ?? new())).Append(',').Append(string.Join(' ', p.BuiltRounds ?? new())).Append(',')
                  .Append(string.Join(' ', p.Tiles ?? new())).Append(',').Append(p.Coins).Append(',').Append(p.Shipments);
            var bytes = Encoding.UTF8.GetBytes(sb.Append('\n').ToString());
            sha.TransformBlock(bytes, 0, bytes.Length, null, 0);
        }
        sha.TransformFinalBlock(Array.Empty<byte>(), 0, 0);
        return Convert.ToHexString(sha.Hash!).ToLowerInvariant();
    }

    internal sealed record StrategyParams(int Revision, SortedDictionary<string, int> Revisions, SortedDictionary<string, SortedDictionary<string, JsonElement>> Params);

    /// <summary>Revision and resolved default parameters of every strategy (rule-based is its profiles) for 3 and 4 players.</summary>
    internal static SortedDictionary<string, StrategyParams> CurrentStrategyParams()
    {
        var all = new SortedDictionary<string, StrategyParams>(StringComparer.Ordinal);
        foreach (var name in StrategyRegistry.Revisions.Keys.OrderBy(n => n, StringComparer.Ordinal))
        {
            var r3 = StrategyRegistry.Resolve(new SeatConfig { Id = "x", Strategy = name }, 3);
            var r4 = StrategyRegistry.Resolve(new SeatConfig { Id = "x", Strategy = name }, 4);
            all[name] = new StrategyParams(StrategyRegistry.Revisions[name], new(r4.Revisions, StringComparer.Ordinal),
                new(StringComparer.Ordinal) { ["3"] = new(r3.Params, StringComparer.Ordinal), ["4"] = new(r4.Params, StringComparer.Ordinal) });
        }
        return all;
    }

    private static string Canon(object o) => JsonSerializer.Serialize(JsonSerializer.SerializeToElement(o));

    [Fact]
    public void Engine_Behaviour_Matches_The_Golden_Hashes()
    {
        var rules = new SortedDictionary<string, string> { ["3p"] = HashOf(RulesCase(3)), ["4p"] = HashOf(RulesCase(4)) };
        var hashes = new SortedDictionary<string, (string H3, string H4)>(StringComparer.Ordinal);
        foreach (var name in GoldenStrategies)
            hashes[name] = (HashOf(StrategyCase(name, 3)), HashOf(StrategyCase(name, 4)));
        var currentParams = CurrentStrategyParams();

        if (Environment.GetEnvironmentVariable("PR_UPDATE_GOLDEN") == "1")
        {
            var golden = new SortedDictionary<string, object>
            {
                ["note"] = "Golden hashes of fixed games (Tests/VersionTests.cs). Regenerate with PR_UPDATE_GOLDEN=1 dotnet test --filter Golden, only after deciding the versions (CLAUDE.md, 版本與 hash).",
                ["rulesRevision"] = EngineInfo.RulesRevision,
                ["rules"] = rules,
                ["strategies"] = hashes.ToDictionary(kv => kv.Key, kv => (object)new { revision = StrategyRegistry.Revisions[kv.Key], h3 = kv.Value.H3, h4 = kv.Value.H4 }),
            };
            File.WriteAllText(GoldenPath, JsonSerializer.Serialize(golden, Pretty) + "\n");
            var paramsDoc = new SortedDictionary<string, object>
            {
                ["note"] = "Every strategy's logic revision and resolved default parameters per player count, written by PR_UPDATE_GOLDEN=1 dotnet test --filter Golden (checked by Tests/VersionTests.cs). The ML tools use it to predict the hash of a run. Do not edit by hand.",
                ["strategies"] = currentParams,
            };
            File.WriteAllText(ParamsPath, JsonSerializer.Serialize(paramsDoc, Pretty) + "\n");
            return;
        }

        using var doc = JsonDocument.Parse(File.ReadAllText(GoldenPath));
        using var recorded = JsonDocument.Parse(File.ReadAllText(ParamsPath));
        var root = doc.RootElement;
        var problems = new List<string>();
        const string Refresh = "then refresh the golden files: PR_UPDATE_GOLDEN=1 dotnet test --filter Golden";

        int goldenRevision = root.GetProperty("rulesRevision").GetInt32();
        bool rulesChanged = rules["3p"] != root.GetProperty("rules").GetProperty("3p").GetString() || rules["4p"] != root.GetProperty("rules").GetProperty("4p").GetString();
        if (rulesChanged && goldenRevision == EngineInfo.RulesRevision)
            problems.Add($"RULES: games of random players changed: the rules, the RNG / seed derivation or the random strategy changed. If intended: RulesRevision {EngineInfo.RulesRevision} -> {EngineInfo.RulesRevision + 1}, " +
                         "engine version at least a MINOR bump, entries in docs/versions.json, " + Refresh + "; tell the user which data and models are now stale.");
        else if (goldenRevision != EngineInfo.RulesRevision || rulesChanged)
            problems.Add($"RulesRevision is {EngineInfo.RulesRevision} but the golden files were recorded for {goldenRevision}: " + Refresh + ".");

        var recStrategies = recorded.RootElement.GetProperty("strategies");
        foreach (var (name, now) in currentParams)
        {
            if (!recStrategies.TryGetProperty(name, out var was))
            {
                problems.Add($"{name}: missing in ml/strategy-params.json (new strategy?): add it to docs/versions.json and " + Refresh + ".");
                continue;
            }
            bool paramsChanged = Canon(was.GetProperty("params")) != Canon(now.Params);
            bool revisionChanged = was.GetProperty("revision").GetInt32() != StrategyRegistry.Revisions[name];
            bool behaviourChanged = false;
            if (!rulesChanged && hashes.TryGetValue(name, out var h))
            {
                var g = root.GetProperty("strategies").GetProperty(name);
                behaviourChanged = h.H3 != g.GetProperty("h3").GetString() || h.H4 != g.GetProperty("h4").GetString();
            }
            if (revisionChanged)
                problems.Add($"{name}: revision is now {StrategyRegistry.Revisions[name]} (recorded {was.GetProperty("revision").GetInt32()}): add the entry to docs/versions.json and " + Refresh + ".");
            else if (paramsChanged)
                problems.Add($"{name}: default parameters changed ({Diff(was.GetProperty("params"), now.Params)}). A changed default needs NO version (the resolved parameters are in the hash): " +
                             $"{Refresh}. If its decision logic changed too, bump its revision to {StrategyRegistry.Revisions[name] + 1} first.");
            else if (behaviourChanged)
                problems.Add($"{name}: decisions changed with the same parameters = its logic (or code it shares: HeuristicStrategy, TieBreakRules) changed. If intended: " +
                             $"StrategyRegistry.Revisions[\"{name}\"] {StrategyRegistry.Revisions[name]} -> {StrategyRegistry.Revisions[name] + 1}, engine version at least a MINOR bump, entries in docs/versions.json, {Refresh}; tell the user which data is now stale.");
        }
        Assert.True(problems.Count == 0, "Engine behaviour or versions differ from the golden files:\n- " + string.Join("\n- ", problems));
    }

    private static string Diff(JsonElement was, object now)
    {
        var a = JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, JsonElement>>>(was.GetRawText())!;
        var b = JsonSerializer.Deserialize<Dictionary<string, Dictionary<string, JsonElement>>>(JsonSerializer.Serialize(now, Pretty))!; // same escaping as the file
        var parts = new List<string>();
        foreach (var players in a.Keys.Union(b.Keys).OrderBy(k => k))
        {
            a.TryGetValue(players, out var pa); b.TryGetValue(players, out var pb);
            pa ??= new(); pb ??= new();
            foreach (var key in pa.Keys.Union(pb.Keys).OrderBy(k => k, StringComparer.Ordinal))
            {
                string x = pa.TryGetValue(key, out var vx) ? vx.GetRawText() : "-", y = pb.TryGetValue(key, out var vy) ? vy.GetRawText() : "-";
                if (x != y) parts.Add($"{players}p {key}: {x} -> {y}");
            }
        }
        return string.Join("; ", parts);
    }

    internal static string EngineInfoPath => Path.Combine(RepoRoot(), "ml", "engine-info.json");

    /// <summary>What the ML tools need to know about this engine (ml/engine-info.json; fingerprint.engine_info reads it).</summary>
    internal static string CurrentEngineInfo() => JsonSerializer.Serialize(new
    {
        note = "The engine's version numbers and the lists the ML UI shares with the Dashboard, written by PR_UPDATE_GOLDEN=1 dotnet test --filter Golden (checked by Tests/VersionTests.cs). ml/fingerprint.py and the ML UI read it instead of the C# source. Do not edit by hand.",
        engineVersion = EngineInfo.Version,
        rulesVersion = EngineInfo.RulesVersion,
        rulesRevision = EngineInfo.RulesRevision,
        featureVersion = FeatureSets.LatestVersion,
        formatVersion = PositionDump.FormatVersion,
        defaultLeafRollout = MctsStrategy.DefaultLeafRollout,
        strategies = StrategyRegistry.Names.ToArray(),
        handWritten = StrategyRegistry.HandWrittenNames.ToArray(),
        seatOrders = SeatParams.SeatOrders,
        mctsParamOrder = SeatParams.MctsFirst,
    }, Pretty) + "\n";

    [Fact]
    public void Engine_Info_File_Matches_The_Code()
    {
        string now = CurrentEngineInfo();
        if (Environment.GetEnvironmentVariable("PR_UPDATE_GOLDEN") == "1")
        {
            File.WriteAllText(EngineInfoPath, now);
            return;
        }
        string was = File.Exists(EngineInfoPath) ? File.ReadAllText(EngineInfoPath).Replace("\r\n", "\n") : "";
        Assert.True(was == now, "ml/engine-info.json differs from the engine (a version number, a strategy or a shared list changed): " +
                                "refresh it with PR_UPDATE_GOLDEN=1 dotnet test --filter Golden.");
    }

    [Fact]
    public void Every_Strategy_Has_A_Revision()
    {
        foreach (var name in StrategyRegistry.Names.Where(n => !n.Equals("rule-based", StringComparison.OrdinalIgnoreCase)))
            Assert.True(StrategyRegistry.Revisions.ContainsKey(name), $"{name}: no entry in StrategyRegistry.Revisions");
    }

    [Fact]
    public void Version_List_Names_The_Current_Version_Of_Every_Track_And_Strategy()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(RepoRoot(), "docs", "versions.json")));
        var latest = doc.RootElement.GetProperty("tracks").EnumerateArray().ToDictionary(
            t => t.GetProperty("id").GetString()!, t => t.GetProperty("entries")[0].GetProperty("version").GetString());
        Assert.Equal(EngineInfo.RulesRevision.ToString(), latest["rules"]);
        Assert.Equal(EngineInfo.Version, latest["engine"]);
        Assert.Equal(FeatureSets.LatestVersion.ToString(), latest["features"]);
        Assert.Equal(PositionDump.FormatVersion.ToString(), latest["format"]);
        var strategies = doc.RootElement.GetProperty("strategies").EnumerateArray().ToDictionary(
            t => t.GetProperty("id").GetString()!, t => t.GetProperty("entries")[0].GetProperty("version").GetString());
        foreach (var (name, revision) in StrategyRegistry.Revisions)
            Assert.True(strategies.TryGetValue(name, out var v) && v == revision.ToString(), $"docs/versions.json: strategy {name} should list revision {revision} first");
        foreach (var list in new[] { "tracks", "strategies" })
            foreach (var track in doc.RootElement.GetProperty(list).EnumerateArray())
                foreach (var e in track.GetProperty("entries").EnumerateArray())
                    Assert.True(e.GetProperty("changes").GetArrayLength() > 0, $"{track.GetProperty("id").GetString()} {e.GetProperty("version").GetString()}: no changes listed");
    }

    [Fact]
    public void Commit_Is_Known_Or_Unknown_But_Never_Empty()
    {
        Assert.False(string.IsNullOrWhiteSpace(EngineInfo.Commit));
    }
}

/// <summary>StrategyRegistry.Resolve: the parameters a seat really plays with.</summary>
public class ResolveTests
{
    private static ResolvedSeat R(string strategy, int players, string? json = null) => StrategyRegistry.Resolve(new SeatConfig
    {
        Id = "a", Strategy = strategy,
        Params = json == null ? new() : JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(json)!,
    }, players);

    [Fact]
    public void Defaults_Are_Filled_In_Per_Player_Count_And_Config_Values_Win()
    {
        var p3 = R("corn-to-premium", 3);
        var p4 = R("corn-to-premium", 4);
        Assert.True(p3.Params.ContainsKey("buildThreshold") && p3.Params.ContainsKey("randomTies"));
        Assert.Equal(new Dictionary<string, int> { ["corn-to-premium"] = 1 }, p4.Revisions);
        var mine = R("corn-to-premium", 4, "{\"buildThreshold\": 9.5}");
        Assert.Equal(9.5, mine.Params["buildThreshold"].GetDouble());
        Assert.Equal(p4.Params.Count, mine.Params.Count);
        Assert.True(p3.Params.Keys.SequenceEqual(p4.Params.Keys));
    }

    [Fact]
    public void Unread_Config_Params_Are_Kept_So_A_Typo_Still_Changes_The_Hash()
    {
        var seat = R("build-first", 4, "{\"buildTreshold\": 3}");
        Assert.Equal(3, seat.Params["buildTreshold"].GetDouble());
    }

    [Fact]
    public void Mcts_Includes_Its_Rollout_Strategy_And_RuleBased_Is_Its_Profile()
    {
        var mcts = R("mcts", 4, "{\"rolloutStrategy\": \"guided-random\"}");
        Assert.Equal(new[] { "guided-random", "mcts" }, mcts.Revisions.Keys.OrderBy(k => k));
        Assert.Equal(200, mcts.Params["simulations"].GetDouble());
        var rb = R("rule-based", 4, "{\"profile\": \"harbor-rush\"}");
        Assert.Equal(new[] { "harbor-rush" }, rb.Revisions.Keys);
        Assert.Equal("harbor-rush", rb.Params["profile"].GetString());
    }

    [Fact]
    public void Results_And_Dumps_Record_The_Resolved_Seats()
    {
        var cfg = new SimulationConfig { Players = 3, Games = 2, Seed = 5, Seats = new() { new() { Id = "a", Strategy = "corn-shipper" }, new() { Id = "b", Strategy = "random" }, new() { Id = "c", Strategy = "random" } } };
        var result = BatchSimulator.Run(cfg, new BatchOptions(), CancellationToken.None);
        Assert.Equal(3, result.ResolvedSeats!.Count);
        Assert.Contains("buildThreshold", result.ResolvedSeats[0].Params.Keys);
        string path = Path.Combine(Path.GetTempPath(), $"res-{Guid.NewGuid():N}.bin");
        try
        {
            PositionDump.Run(cfg, path, 0.5);
            using var doc = JsonDocument.Parse(File.ReadAllText(path + ".json"));
            Assert.Equal("base", doc.RootElement.GetProperty("rulesVersion").GetString());
            Assert.Equal(1, doc.RootElement.GetProperty("resolvedSeats")[0].GetProperty("revisions").GetProperty("corn-shipper").GetInt32());
        }
        finally
        {
            File.Delete(path);
            File.Delete(path + ".json");
        }
    }
}
