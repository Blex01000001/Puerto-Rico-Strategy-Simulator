namespace Dashboard.Services;

/// <summary>Colour and display name per strategy. Colour follows the strategy (entity), never its rank.</summary>
public static class Palette
{
    private static readonly Dictionary<string, int> Slots = new(StringComparer.OrdinalIgnoreCase)
    {
        ["corn-shipper"] = 1,     // blue
        ["corn-to-premium"] = 2,  // orange
        ["harbor-rush"] = 3,      // aqua
        ["build-first"] = 4,      // yellow
        ["random"] = 5,           // magenta
        ["mcts"] = 6,             // green
        ["cheap-engine"] = 7,     // violet
        ["wharf-rush"] = 8,       // red
        ["corn-monopoly"] = 9,    // lime
        ["wharf-premium"] = 10,   // brown
        ["corn-monopoly-tiles"] = 11, // teal
        ["corn-monopoly-hoard"] = 12, // grey-blue
    };

    /// <summary>CSS variable for the series colour (1..8); unknown strategies take the remaining slots by position.</summary>
    public static string Color(string strategy, int fallbackIndex) =>
        $"var(--series-{(Slots.TryGetValue(strategy, out int s) ? s : 6 + Math.Abs(fallbackIndex) % 3)})";

    /// <summary>Icon shown in front of a strategy's title in the strategy descriptions.</summary>
    public static string Icon(string strategy) => strategy.ToLowerInvariant() switch
    {
        "corn-shipper" => "🌽",
        "corn-to-premium" => "☕",
        "harbor-rush" => "⚓",
        "build-first" => "🏗️",
        "cheap-engine" => "⚙️",
        "wharf-rush" => "🚢",
        "corn-monopoly" => "😈",
        "wharf-premium" => "⛵",
        "corn-monopoly-tiles" => "🧺",
        "corn-monopoly-hoard" => "📦",
        "mcts" => "🌳",
        "random" => "🎲",
        "guided-random" => "🧭",
        _ => "🎯",
    };

    /// <summary>Chinese label of a seat-order mode.</summary>
    public static string SeatOrderLabel(PuertoRico.Engine.Simulation.SeatOrderMode mode) => mode switch
    {
        PuertoRico.Engine.Simulation.SeatOrderMode.Random => "隨機",
        PuertoRico.Engine.Simulation.SeatOrderMode.Balanced => "完全平衡",
        PuertoRico.Engine.Simulation.SeatOrderMode.Rotate => "輪換",
        PuertoRico.Engine.Simulation.SeatOrderMode.Fixed => "固定",
        _ => mode.ToString(),
    };

    /// <summary>Display name of a strategy: "mcts" in capitals, the others as PascalCase words joined by "-" (corn-shipper → Corn-Shipper).</summary>
    public static string DisplayName(string strategy) =>
        strategy.Equals("mcts", StringComparison.OrdinalIgnoreCase)
            ? "MCTS"
            : strategy.Equals("random", StringComparison.OrdinalIgnoreCase)
            ? "Full-Random" // not just "Random": guided-random is also random
            : string.Join("-", strategy.Split('-').Select(w => w.Length == 0 ? w : char.ToUpperInvariant(w[0]) + w[1..]));

    public static string Label(string seatId, string strategy) =>
        string.Equals(seatId, strategy, StringComparison.OrdinalIgnoreCase) ? DisplayName(strategy) : $"{seatId} · {DisplayName(strategy)}";
}
