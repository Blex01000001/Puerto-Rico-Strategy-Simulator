using System.Text.Json;
using PuertoRico.Engine.Simulation;

namespace PuertoRico.Engine.Strategies;

/// <summary>Creates strategies by the name used in config files. New strategies register here.</summary>
public static class StrategyRegistry
{
    public delegate IStrategy Factory(IReadOnlyDictionary<string, JsonElement> parameters, ulong seed, int seat);

    private static readonly Dictionary<string, Factory> Factories = new(StringComparer.OrdinalIgnoreCase)
    {
        ["random"] = (_, seed, _) => new RandomStrategy(seed),
        ["corn-shipper"] = (p, seed, _) => Seeded(new RuleBased.CornShipperStrategy(p), seed),
        ["corn-to-premium"] = (p, seed, _) => Seeded(new RuleBased.CornToPremiumStrategy(p), seed),
        ["harbor-rush"] = (p, seed, _) => Seeded(new RuleBased.HarborRushStrategy(p), seed),
        ["build-first"] = (p, seed, _) => Seeded(new RuleBased.BuildFirstStrategy(p), seed),
        ["cheap-engine"] = (p, seed, _) => Seeded(new RuleBased.CheapEngineStrategy(p), seed),
        ["wharf-rush"] = (p, seed, _) => Seeded(new RuleBased.WharfRushStrategy(p), seed),
        ["wharf-premium"] = (p, seed, _) => Seeded(new RuleBased.WharfPremiumStrategy(p), seed),
        ["corn-monopoly"] = (p, seed, _) => Seeded(new RuleBased.CornMonopolyStrategy(p), seed),
        ["corn-monopoly-tiles"] = (p, seed, _) => Seeded(new RuleBased.CornMonopolyStrategy(p, grab: true, hoard: false), seed),
        ["corn-monopoly-hoard"] = (p, seed, _) => Seeded(new RuleBased.CornMonopolyStrategy(p, grab: false, hoard: true), seed),
        // "rule-based" selects a hand-written profile by params.profile (default corn-shipper).
        ["rule-based"] = (p, seed, seat) =>
        {
            string profile = GetString(p, "profile", "corn-shipper");
            return profile.ToLowerInvariant() switch
            {
                "corn-shipper" => Seeded(new RuleBased.CornShipperStrategy(p), seed),
                "corn-to-premium" => Seeded(new RuleBased.CornToPremiumStrategy(p), seed),
                "harbor-rush" => Seeded(new RuleBased.HarborRushStrategy(p), seed),
                "build-first" => Seeded(new RuleBased.BuildFirstStrategy(p), seed),
                "cheap-engine" => Seeded(new RuleBased.CheapEngineStrategy(p), seed),
                "wharf-rush" => Seeded(new RuleBased.WharfRushStrategy(p), seed),
                "wharf-premium" => Seeded(new RuleBased.WharfPremiumStrategy(p), seed),
                "corn-monopoly" => Seeded(new RuleBased.CornMonopolyStrategy(p), seed),
                "corn-monopoly-tiles" => Seeded(new RuleBased.CornMonopolyStrategy(p, grab: true, hoard: false), seed),
                "corn-monopoly-hoard" => Seeded(new RuleBased.CornMonopolyStrategy(p, grab: false, hoard: true), seed),
                _ => throw new ArgumentException($"Unknown rule-based profile '{profile}'. Known: corn-shipper, corn-to-premium, harbor-rush, build-first, cheap-engine, wharf-rush, wharf-premium, corn-monopoly, corn-monopoly-tiles, corn-monopoly-hoard"),
            };
        },
        ["guided-random"] = (_, seed, _) => new GuidedRandomStrategy(seed),
        ["mcts"] = (p, seed, _) => new Mcts.MctsStrategy(p, seed),
    };

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

    public static bool IsKnown(string name) => Factories.ContainsKey(name);

    public static IStrategy Create(string name, IReadOnlyDictionary<string, JsonElement> parameters, ulong seed, int seat)
    {
        if (!Factories.TryGetValue(name, out var factory))
            throw new ArgumentException($"Unknown strategy '{name}'. Known: {string.Join(", ", Factories.Keys)}");
        return factory(parameters, seed, seat);
    }
}
