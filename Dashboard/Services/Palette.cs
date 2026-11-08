namespace Dashboard.Services;

/// <summary>Colour and display-name per strategy. Colour follows the strategy (entity), never its rank.</summary>
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
    };

    private static readonly Dictionary<string, string> Names = new(StringComparer.OrdinalIgnoreCase)
    {
        ["corn-shipper"] = "玉米出貨流",
        ["corn-to-premium"] = "玉米轉菸草／咖啡流",
        ["harbor-rush"] = "港口流",
        ["build-first"] = "建築優先流",
        ["random"] = "隨機",
        ["mcts"] = "MCTS 搜尋",
        ["cheap-engine"] = "便宜引擎流",
    };

    /// <summary>CSS variable for the series colour (1..8); unknown strategies take the remaining slots by position.</summary>
    public static string Color(string strategy, int fallbackIndex) =>
        $"var(--series-{(Slots.TryGetValue(strategy, out int s) ? s : 6 + Math.Abs(fallbackIndex) % 3)})";

    /// <summary>Chinese label of a seat-order mode.</summary>
    public static string SeatOrderLabel(PuertoRico.Engine.Simulation.SeatOrderMode mode) => mode switch
    {
        PuertoRico.Engine.Simulation.SeatOrderMode.Random => "隨機",
        PuertoRico.Engine.Simulation.SeatOrderMode.Balanced => "完全平衡",
        PuertoRico.Engine.Simulation.SeatOrderMode.Rotate => "輪換",
        PuertoRico.Engine.Simulation.SeatOrderMode.Fixed => "固定",
        _ => mode.ToString(),
    };

    public static string DisplayName(string strategy) => Names.TryGetValue(strategy, out var n) ? n : strategy;

    public static string Label(string seatId, string strategy) =>
        string.Equals(seatId, strategy, StringComparison.OrdinalIgnoreCase) ? DisplayName(strategy) : $"{seatId} · {DisplayName(strategy)}";
}
