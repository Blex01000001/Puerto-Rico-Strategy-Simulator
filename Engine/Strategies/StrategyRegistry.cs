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
                _ => throw new ArgumentException($"Unknown rule-based profile '{profile}'. Known: corn-shipper, corn-to-premium, harbor-rush, build-first"),
            };
        },
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
