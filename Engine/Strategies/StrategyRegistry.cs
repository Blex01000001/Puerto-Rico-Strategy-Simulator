using System.Text.Json;
using PuertoRico.Engine.Simulation;

namespace PuertoRico.Engine.Strategies;

/// <summary>Creates strategies by the name used in config files. New strategies register here.</summary>
public static class StrategyRegistry
{
    public delegate IStrategy Factory(IReadOnlyDictionary<string, JsonElement> parameters, ulong seed, int seat);

    /// <summary>
    /// Hand-written strategies (<see cref="RuleBased.HeuristicStrategy"/> subclasses): each is registered under its name and
    /// is also a profile of "rule-based". A new hand-written strategy only goes here (plus its revision below).
    /// </summary>
    private static readonly Dictionary<string, Func<IReadOnlyDictionary<string, JsonElement>, RuleBased.HeuristicStrategy>> HandWritten =
        new(StringComparer.OrdinalIgnoreCase)
        {
            ["corn-shipper"] = p => new RuleBased.CornShipperStrategy(p),
            ["corn-to-premium"] = p => new RuleBased.CornToPremiumStrategy(p),
            ["harbor-rush"] = p => new RuleBased.HarborRushStrategy(p),
            ["build-first"] = p => new RuleBased.BuildFirstStrategy(p),
            ["cheap-engine"] = p => new RuleBased.CheapEngineStrategy(p),
            ["wharf-rush"] = p => new RuleBased.WharfRushStrategy(p),
            ["wharf-premium"] = p => new RuleBased.WharfPremiumStrategy(p),
            ["corn-monopoly"] = p => new RuleBased.CornMonopolyStrategy(p),
            ["corn-monopoly-tiles"] = p => new RuleBased.CornMonopolyStrategy(p, grab: true, hoard: false),
            ["corn-monopoly-hoard"] = p => new RuleBased.CornMonopolyStrategy(p, grab: false, hoard: true),
        };

    /// <summary>Every registered name (in this order: random, the hand-written ones, rule-based, guided-random, mcts).</summary>
    private static readonly Dictionary<string, Factory> Factories = BuildFactories();

    private static Dictionary<string, Factory> BuildFactories()
    {
        var factories = new Dictionary<string, Factory>(StringComparer.OrdinalIgnoreCase)
        {
            ["random"] = (_, seed, _) => new RandomStrategy(seed),
        };
        foreach (var (name, make) in HandWritten)
            factories[name] = (p, seed, _) => Seeded(make(p), seed);
        // "rule-based" selects a hand-written profile by params.profile (default corn-shipper).
        factories["rule-based"] = (p, seed, _) =>
        {
            string profile = GetString(p, "profile", "corn-shipper");
            if (!HandWritten.TryGetValue(profile, out var make))
                throw new ArgumentException($"Unknown rule-based profile '{profile}'. Known: {string.Join(", ", HandWritten.Keys)}");
            return Seeded(make(p), seed);
        };
        factories["guided-random"] = (_, seed, _) => new GuidedRandomStrategy(seed);
        factories["mcts"] = (p, seed, _) => new Mcts.MctsStrategy(p, seed);
        return factories;
    }

    /// <summary>
    /// Logic revision of every strategy (shown as <c>harbor-rush-v1</c>). Bumped BY HAND when the strategy decides
    /// differently for the same parameters: its decision logic changed, or code it shares changed (HeuristicStrategy,
    /// TieBreakRules: bump every strategy built on it; MCTS also covers the value-model inference and the feature sets code).
    /// Changing a parameter's DEFAULT does not need a bump: the resolved parameters (defaults filled in) are recorded in
    /// result files and dumps and go into the ML hash. Tests/VersionTests.cs (GoldenTests) tells which strategy changed;
    /// docs/versions.json lists what each revision changed. "rule-based" has none of its own: it is its profile.
    /// </summary>
    public static readonly IReadOnlyDictionary<string, int> Revisions = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
    {
        ["random"] = 1,
        ["guided-random"] = 1,
        ["corn-shipper"] = 1,
        ["corn-to-premium"] = 1,
        ["harbor-rush"] = 1,
        ["build-first"] = 1,
        ["cheap-engine"] = 1,
        ["wharf-rush"] = 1,
        ["wharf-premium"] = 1,
        ["corn-monopoly"] = 1,
        ["corn-monopoly-tiles"] = 1,
        ["corn-monopoly-hoard"] = 1,
        ["mcts"] = 1,
    };

    /// <summary>
    /// The seat as it really plays with <paramref name="players"/> players: every parameter the strategy reads, with the
    /// value it uses (config value or this player count's default), plus any config parameter it does not read (kept so
    /// a typo still shows up), and the logic revisions of all strategy code involved (rule-based: its profile; MCTS: also
    /// its rollout strategy). Creates the strategy once without playing (an MCTS value model is loaded).
    /// </summary>
    public static ResolvedSeat Resolve(SeatConfig seat, int players)
    {
        var recorder = new ParamRecorder(seat.Params);
        var strategy = Create(seat.Strategy, recorder, 0, 0);
        if (strategy is IResolvesParameters r) r.ResolveParameters(players);
        var used = new SortedDictionary<string, JsonElement>(recorder.Used, StringComparer.Ordinal);
        foreach (var (key, value) in seat.Params)
            if (!used.ContainsKey(key)) used[key] = value.Clone();
        var revisions = new SortedDictionary<string, int>(StringComparer.Ordinal);
        string name = seat.Strategy.ToLowerInvariant();
        if (name == "rule-based")
        {
            string profile = GetString(seat.Params, "profile", "corn-shipper").ToLowerInvariant();
            revisions[profile] = Revisions[profile];
        }
        else revisions[name] = Revisions[name];
        if (strategy is Mcts.MctsStrategy mcts)
            foreach (var (k, v) in Resolve(new SeatConfig { Strategy = mcts.RolloutStrategy }, players).Revisions) revisions[k] = v;
        return new ResolvedSeat { Id = seat.Id, Strategy = name, Revisions = new(revisions), Params = new(used) };
    }

    /// <summary>All seats of a config, resolved for its player count (written into result files and dumps).</summary>
    public static List<ResolvedSeat> ResolveSeats(SimulationConfig cfg) => cfg.Seats.Select(s => Resolve(s, cfg.Players)).ToList();

    /// <summary>Gives a hand-written strategy its seed (only used by the optional random tie-break, <c>randomTies</c>).</summary>
    private static IStrategy Seeded(RuleBased.HeuristicStrategy strategy, ulong seed)
    {
        strategy.Seed = seed;
        return strategy;
    }

    /// <summary>Every strategy reads its parameters through these two (so <see cref="Resolve"/> sees the values used).</summary>
    public static double GetDouble(IReadOnlyDictionary<string, JsonElement> p, string key, double fallback)
    {
        double value = p.TryGetValue(key, out var e) && e.ValueKind == JsonValueKind.Number ? e.GetDouble() : fallback;
        if (p is ParamRecorder r) r.Record(key, value);
        return value;
    }

    public static string GetString(IReadOnlyDictionary<string, JsonElement> p, string key, string fallback)
    {
        string value = p.TryGetValue(key, out var e) && e.ValueKind == JsonValueKind.String ? e.GetString() ?? fallback : fallback;
        if (p is ParamRecorder r) r.Record(key, value);
        return value;
    }

    public static IEnumerable<string> Names => Factories.Keys;

    /// <summary>The hand-written strategies (also the profiles "rule-based" accepts), in registration order.</summary>
    public static IEnumerable<string> HandWrittenNames => HandWritten.Keys;

    public static bool IsKnown(string name) => Factories.ContainsKey(name);

    public static IStrategy Create(string name, IReadOnlyDictionary<string, JsonElement> parameters, ulong seed, int seat)
    {
        if (!Factories.TryGetValue(name, out var factory))
            throw new ArgumentException($"Unknown strategy '{name}'. Known: {string.Join(", ", Factories.Keys)}");
        return factory(parameters, seed, seat);
    }
}
