using System.Text.Json;

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

    /// <summary>Gives a hand-written strategy its seed (only used by the optional random tie-break, <c>randomTies</c>).</summary>
    private static IStrategy Seeded(RuleBased.HeuristicStrategy strategy, ulong seed)
    {
        strategy.Seed = seed;
        return strategy;
    }

    public static double GetDouble(IReadOnlyDictionary<string, JsonElement> p, string key, double fallback) =>
        p.TryGetValue(key, out var e) && e.ValueKind == JsonValueKind.Number ? e.GetDouble() : fallback;

    public static string GetString(IReadOnlyDictionary<string, JsonElement> p, string key, string fallback) =>
        p.TryGetValue(key, out var e) && e.ValueKind == JsonValueKind.String ? e.GetString() ?? fallback : fallback;

    public static IEnumerable<string> Names => Factories.Keys;

    public static bool IsKnown(string name) => Factories.ContainsKey(name);

    public static IStrategy Create(string name, IReadOnlyDictionary<string, JsonElement> parameters, ulong seed, int seat)
    {
        if (!Factories.TryGetValue(name, out var factory))
            throw new ArgumentException($"Unknown strategy '{name}'. Known: {string.Join(", ", Factories.Keys)}");
        return factory(parameters, seed, seat);
    }
}
