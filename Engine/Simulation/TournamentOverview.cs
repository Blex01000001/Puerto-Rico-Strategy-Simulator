namespace PuertoRico.Engine.Simulation;

/// <summary>One result file reduced to what the overview needs (no per-game records).</summary>
public sealed class OverviewTable
{
    public string Name { get; set; } = "";
    public int Players { get; set; }
    public int Games { get; set; }
    public ulong Seed { get; set; }
    public List<SeatSummary> Seats { get; set; } = new();
}

/// <summary>One strategy aggregated over all tables with the same player count.</summary>
public sealed class OverviewStrategyRow
{
    public int Players { get; set; }
    public string Strategy { get; set; } = "";
    public int Tables { get; set; }
    public int Games { get; set; }
    /// <summary>Mean of the win share over the tables it played in (every table counts the same).</summary>
    public double AvgWinShare { get; set; }
    public double AvgScore { get; set; }
    /// <summary>AvgWinShare minus the even-split baseline 1/players; &gt; 0 = better than an equal seat.</summary>
    public double Edge => AvgWinShare - 1.0 / Players;
    public double MinWinShare { get; set; }
    public double MaxWinShare { get; set; }
}

/// <summary>Cross-table summary for the Dashboard overview page (UI-free, testable).</summary>
public static class TournamentOverview
{
    public static OverviewTable FromResult(string name, SimulationResult r) => new()
    {
        Name = name,
        Players = r.Config.Players,
        Games = r.GamesCompleted,
        Seed = r.Config.Seed,
        Seats = r.Summary,
    };

    /// <summary>Per (players, strategy): averages over the tables it appeared in, ordered by players then best win share.
    /// A strategy seated twice at one table counts once per table (its seats are averaged).</summary>
    public static List<OverviewStrategyRow> Summarize(IEnumerable<OverviewTable> tables)
    {
        var acc = new Dictionary<(int Players, string Strategy), List<(double Win, double Score, int Games)>>();
        foreach (var t in tables)
            foreach (var g in t.Seats.GroupBy(s => s.Strategy, StringComparer.OrdinalIgnoreCase))
            {
                var key = (t.Players, g.Key.ToLowerInvariant());
                if (!acc.TryGetValue(key, out var list)) acc[key] = list = new();
                list.Add((g.Average(s => s.WinShare), g.Average(s => s.AvgScore), g.Sum(s => s.Games)));
            }

        return acc.Select(kv => new OverviewStrategyRow
            {
                Players = kv.Key.Players,
                Strategy = kv.Key.Strategy,
                Tables = kv.Value.Count,
                Games = kv.Value.Sum(v => v.Games),
                AvgWinShare = kv.Value.Average(v => v.Win),
                AvgScore = kv.Value.Average(v => v.Score),
                MinWinShare = kv.Value.Min(v => v.Win),
                MaxWinShare = kv.Value.Max(v => v.Win),
            })
            .OrderBy(r => r.Players).ThenByDescending(r => r.AvgWinShare).ToList();
    }
}
