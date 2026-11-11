using System.Text.Json;

namespace PuertoRico.Engine.Strategies;

/// <summary>Creates strategies by the name used in config files. New strategies register here.</summary>
public static class StrategyRegistry
{
    public delegate IStrategy Factory(IReadOnlyDictionary<string, JsonElement> parameters, ulong seed, int seat);

    private static readonly Dictionary<string, Factory> Factories = new(StringComparer.OrdinalIgnoreCase)
    {
        ["random"] = (_, seed, _) => new RandomStrategy(seed),
        ["corn-shipper"] = (p, _, _) => new RuleBased.CornShipperStrategy(p),
        ["corn-to-premium"] = (p, _, _) => new RuleBased.CornToPremiumStrategy(p),
        ["harbor-rush"] = (p, _, _) => new RuleBased.HarborRushStrategy(p),
        ["build-first"] = (p, _, _) => new RuleBased.BuildFirstStrategy(p),
        ["cheap-engine"] = (p, _, _) => new RuleBased.CheapEngineStrategy(p),
        ["wharf-rush"] = (p, _, _) => new RuleBased.WharfRushStrategy(p),
        ["wharf-premium"] = (p, _, _) => new RuleBased.WharfPremiumStrategy(p),
        ["corn-monopoly"] = (p, _, _) => new RuleBased.CornMonopolyStrategy(p),
        ["corn-monopoly-tiles"] = (p, _, _) => new RuleBased.CornMonopolyStrategy(p, grab: true, hoard: false),
        ["corn-monopoly-hoard"] = (p, _, _) => new RuleBased.CornMonopolyStrategy(p, grab: false, hoard: true),
        // "rule-based" selects a hand-written profile by params.profile (default corn-shipper).
        ["rule-based"] = (p, seed, seat) =>
        {
            string profile = GetString(p, "profile", "corn-shipper");
            return profile.ToLowerInvariant() switch
            {
                "corn-shipper" => new RuleBased.CornShipperStrategy(p),
                "corn-to-premium" => new RuleBased.CornToPremiumStrategy(p),
                "harbor-rush" => new RuleBased.HarborRushStrategy(p),
                "build-first" => new RuleBased.BuildFirstStrategy(p),
                "cheap-engine" => new RuleBased.CheapEngineStrategy(p),
                "wharf-rush" => new RuleBased.WharfRushStrategy(p),
                "wharf-premium" => new RuleBased.WharfPremiumStrategy(p),
                "corn-monopoly" => new RuleBased.CornMonopolyStrategy(p),
                "corn-monopoly-tiles" => new RuleBased.CornMonopolyStrategy(p, grab: true, hoard: false),
                "corn-monopoly-hoard" => new RuleBased.CornMonopolyStrategy(p, grab: false, hoard: true),
                _ => throw new ArgumentException($"Unknown rule-based profile '{profile}'. Known: corn-shipper, corn-to-premium, harbor-rush, build-first, cheap-engine, wharf-rush, wharf-premium, corn-monopoly, corn-monopoly-tiles, corn-monopoly-hoard"),
            };
        },
        ["guided-random"] = (_, seed, _) => new GuidedRandomStrategy(seed),
        ["mcts"] = (p, seed, _) => new Mcts.MctsStrategy(p, seed),
    };

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
