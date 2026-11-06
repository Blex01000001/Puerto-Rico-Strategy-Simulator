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
        // "rule-based" selects a hand-written profile by params.profile (default corn-shipper).
        ["rule-based"] = (p, seed, seat) =>
        {
            string profile = GetString(p, "profile", "corn-shipper");
            if (profile.Equals("corn-shipper", StringComparison.OrdinalIgnoreCase)) return new RuleBased.CornShipperStrategy(p);
            throw new ArgumentException($"Unknown rule-based profile '{profile}'. Known: corn-shipper");
        },
        // Reserved: "mcts".
    };

    public static double GetDouble(IReadOnlyDictionary<string, JsonElement> p, string key, double fallback) =>
        p.TryGetValue(key, out var e) && e.ValueKind == JsonValueKind.Number ? e.GetDouble() : fallback;

    public static string GetString(IReadOnlyDictionary<string, JsonElement> p, string key, string fallback) =>
        p.TryGetValue(key, out var e) && e.ValueKind == JsonValueKind.String ? e.GetString() ?? fallback : fallback;

    public static bool IsKnown(string name) => Factories.ContainsKey(name);

    public static IStrategy Create(string name, IReadOnlyDictionary<string, JsonElement> parameters, ulong seed, int seat)
    {
        if (!Factories.TryGetValue(name, out var factory))
            throw new ArgumentException($"Unknown strategy '{name}'. Known: {string.Join(", ", Factories.Keys)}");
        return factory(parameters, seed, seat);
    }
}
