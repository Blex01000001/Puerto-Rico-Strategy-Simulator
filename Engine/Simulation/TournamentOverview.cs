namespace PuertoRico.Engine.Simulation;

/// <summary>One result file reduced to what the overview needs (no per-game records).</summary>
public sealed class OverviewTable
{
    public string Name { get; set; } = "";
    public int Players { get; set; }
    public int Games { get; set; }
    public ulong Seed { get; set; }
    public SeatOrderMode SeatOrder { get; set; } = SeatOrderMode.Random;
    public List<SeatSummary> Seats { get; set; } = new();
    /// <summary>Strategy name per row/column of <see cref="Pairwise"/> (one per seat); empty when the file has no per-game records.</summary>
    public List<string> PairNames { get; set; } = new();
    /// <summary>Pairwise[i][j] = share of games (not tied on rank) where seat i ranked above seat j (NaN on the diagonal), as in <see cref="ResultAnalysis.Pairwise"/>.</summary>
    public List<List<double>> Pairwise { get; set; } = new();
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
    /// <summary>Half-width of the 95% interval of <see cref="AvgWinShare"/> (tables are independent samples).</summary>
    public double AvgWinShareCi95 { get; set; }
    public double MinWinShare { get; set; }
    public double MaxWinShare { get; set; }
}

/// <summary>Cross-table summary for the Dashboard overview page (UI-free, testable).</summary>
public static class TournamentOverview
{
    /// <summary>
    /// How trustworthy the seating of this table is for comparing strategies: <c>balanced</c> with a game count that is a multiple of n! is exact,
    /// <c>random</c> is fair on average, <c>rotate</c> and <c>fixed</c> keep one circular order (results can swing by 20+ points).
    /// </summary>
    public static string SeatOrderQuality(OverviewTable t)
    {
        long perms = t.Players == 3 ? 6 : 24;
        return t.SeatOrder switch
        {
            SeatOrderMode.Balanced => t.Games % perms == 0 ? "exact" : "approx",
            SeatOrderMode.Random => "fair",
            _ => "biased",
        };
    }

    public static OverviewTable FromResult(string name, SimulationResult r, ResultAnalysis? analysis = null)
    {
        var t = new OverviewTable
        {
            Name = name,
            Players = r.Config.Players,
            Games = r.GamesCompleted,
            Seed = r.Config.Seed,
            SeatOrder = r.Config.SeatOrder,
            Seats = r.Summary,
        };
        if (analysis is { HasGameRecords: true })
        {
            t.PairNames = analysis.Strategies.Select(s => s.Strategy).ToList();
            t.Pairwise = analysis.Pairwise;
        }
        return t;
    }

    /// <summary>Per (players, strategy): averages over the tables it appeared in, ordered by players then best win share.
    /// A strategy seated twice at one table counts once per table (its seats are averaged).</summary>
    public static List<OverviewStrategyRow> Summarize(IEnumerable<OverviewTable> tables)
    {
        var acc = new Dictionary<(int Players, string Strategy), List<(double Win, double Score, int Games, double Ci)>>();
        foreach (var t in tables)
            foreach (var g in t.Seats.GroupBy(s => s.Strategy, StringComparer.OrdinalIgnoreCase))
            {
                var key = (t.Players, g.Key.ToLowerInvariant());
                if (!acc.TryGetValue(key, out var list)) acc[key] = list = new();
                double win = g.Average(s => s.WinShare);
                list.Add((win, g.Average(s => s.AvgScore), g.Sum(s => s.Games), ResultAnalysis.Ci(win, (int)g.Average(s => s.Games))));
            }

        return acc.Select(kv => new OverviewStrategyRow
            {
                Players = kv.Key.Players,
                Strategy = kv.Key.Strategy,
                Tables = kv.Value.Count,
                Games = kv.Value.Sum(v => v.Games),
                AvgWinShare = kv.Value.Average(v => v.Win),
                AvgScore = kv.Value.Average(v => v.Score),
                AvgWinShareCi95 = Math.Sqrt(kv.Value.Sum(v => v.Ci * v.Ci)) / kv.Value.Count,
                MinWinShare = kv.Value.Min(v => v.Win),
                MaxWinShare = kv.Value.Max(v => v.Win),
            })
            .OrderBy(r => r.Players).ThenByDescending(r => r.AvgWinShare).ToList();
    }

    /// <summary>Per ordered (players, strategy A, strategy B): share of games A ranked above B, averaged over the tables where both sat
    /// (needs per-game records; seats of the same strategy are skipped).</summary>
    public static List<OverviewPairRow> Pairwise(IEnumerable<OverviewTable> tables)
    {
        var acc = new Dictionary<(int, string, string), List<double>>();
        foreach (var t in tables)
        {
            int n = t.PairNames.Count;
            if (n == 0 || t.Pairwise.Count != n) continue;
            for (int i = 0; i < n; i++)
                for (int j = 0; j < n; j++)
                {
                    if (i == j || string.Equals(t.PairNames[i], t.PairNames[j], StringComparison.OrdinalIgnoreCase)) continue;
                    double v = t.Pairwise[i][j];
                    if (double.IsNaN(v)) continue;
                    var key = (t.Players, t.PairNames[i].ToLowerInvariant(), t.PairNames[j].ToLowerInvariant());
                    if (!acc.TryGetValue(key, out var list)) acc[key] = list = new();
                    list.Add(v);
                }
        }
        return acc.Select(kv => new OverviewPairRow { Players = kv.Key.Item1, A = kv.Key.Item2, B = kv.Key.Item3, Tables = kv.Value.Count, AAboveB = kv.Value.Average() })
            .OrderBy(r => r.Players).ThenBy(r => r.A, StringComparer.Ordinal).ThenBy(r => r.B, StringComparer.Ordinal).ToList();
    }
}

public sealed class OverviewPairRow
{
    public int Players { get; set; }
    public string A { get; set; } = "";
    public string B { get; set; } = "";
    public int Tables { get; set; }
    /// <summary>Mean over tables of the share of games where A ranked above B.</summary>
    public double AAboveB { get; set; }
}
