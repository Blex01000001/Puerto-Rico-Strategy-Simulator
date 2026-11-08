using PuertoRico.Engine.Simulation;
using Xunit;

namespace PuertoRico.Tests;

public class TournamentOverviewTests
{
    private static OverviewTable Table(int players, params (string strategy, double win, double score)[] seats) => new()
    {
        Name = "t", Players = players, Games = 1000,
        Seats = seats.Select((s, i) => new SeatSummary { SeatId = $"s{i}", Strategy = s.strategy, Games = 1000, WinShare = s.win, AvgScore = s.score }).ToList(),
    };

    [Fact]
    public void Averages_over_tables_per_player_count_and_reports_edge()
    {
        var rows = TournamentOverview.Summarize(new[]
        {
            Table(3, ("a", 0.6, 40), ("b", 0.3, 35), ("c", 0.1, 30)),
            Table(3, ("a", 0.2, 36), ("b", 0.5, 38), ("d", 0.3, 33)),
            Table(4, ("a", 0.4, 41), ("b", 0.2, 33), ("c", 0.2, 33), ("d", 0.2, 33)),
        });
        var a3 = rows.Single(r => r.Players == 3 && r.Strategy == "a");
        Assert.Equal(2, a3.Tables);
        Assert.Equal(0.4, a3.AvgWinShare, 6);
        Assert.Equal(38, a3.AvgScore, 6);
        Assert.Equal(0.4 - 1.0 / 3, a3.Edge, 6);
        Assert.Equal(0.2, a3.MinWinShare, 6);
        Assert.Equal(0.6, a3.MaxWinShare, 6);
        Assert.Equal("a", rows.First(r => r.Players == 3).Strategy == "b" ? "b" : "a"); // ordering by players first
        Assert.Equal(new[] { 3, 3, 3, 3, 4, 4, 4, 4 }, rows.Select(r => r.Players).ToArray());
    }

    [Fact]
    public void Strategy_seated_twice_counts_once_per_table()
    {
        var rows = TournamentOverview.Summarize(new[] { Table(3, ("random", 0.2, 30), ("random", 0.4, 32), ("x", 0.4, 33)) });
        var r = rows.Single(x => x.Strategy == "random");
        Assert.Equal(1, r.Tables);
        Assert.Equal(0.3, r.AvgWinShare, 6);
        Assert.Equal(2000, r.Games);
    }
}

public class TournamentOverviewExtraTests
{
    private static OverviewTable Table(int players, string[] names, double[][] pair, params double[] wins) => new()
    {
        Name = "t", Players = players, Games = 1000, PairNames = names.ToList(), Pairwise = pair.Select(r => r.ToList()).ToList(),
        Seats = names.Select((n, i) => new SeatSummary { SeatId = n, Strategy = n, Games = 1000, WinShare = wins[i], AvgScore = 30 }).ToList(),
    };

    [Fact]
    public void Interval_shrinks_with_more_tables()
    {
        var one = TournamentOverview.Summarize(new[] { Table(3, new[] { "a", "b", "c" }, new double[0][], 0.5, 0.3, 0.2) }).Single(r => r.Strategy == "a");
        var three = TournamentOverview.Summarize(Enumerable.Repeat(Table(3, new[] { "a", "b", "c" }, new double[0][], 0.5, 0.3, 0.2), 3)).Single(r => r.Strategy == "a");
        Assert.True(one.AvgWinShareCi95 > 0);
        Assert.Equal(one.AvgWinShareCi95 / Math.Sqrt(3), three.AvgWinShareCi95, 9);
    }

    [Fact]
    public void Pairwise_averages_over_tables_with_both_strategies()
    {
        double n = double.NaN;
        var t1 = Table(3, new[] { "a", "b", "c" }, new[] { new[] { n, 0.7, 0.6 }, new[] { 0.3, n, 0.5 }, new[] { 0.4, 0.5, n } }, 0.4, 0.3, 0.3);
        var t2 = Table(3, new[] { "a", "b", "d" }, new[] { new[] { n, 0.5, 0.8 }, new[] { 0.5, n, 0.4 }, new[] { 0.2, 0.6, n } }, 0.4, 0.3, 0.3);
        var rows = TournamentOverview.Pairwise(new[] { t1, t2 });
        var ab = rows.Single(r => r.A == "a" && r.B == "b");
        Assert.Equal(2, ab.Tables);
        Assert.Equal(0.6, ab.AAboveB, 9);
        Assert.Equal(1, rows.Single(r => r.A == "a" && r.B == "c").Tables);
        Assert.Equal(0.5, rows.Single(r => r.A == "b" && r.B == "c").AAboveB, 9);
    }

    [Fact]
    public void Same_strategy_pairs_and_tables_without_records_are_skipped()
    {
        double n = double.NaN;
        var same = Table(3, new[] { "a", "a", "b" }, new[] { new[] { n, 0.5, 0.6 }, new[] { 0.5, n, 0.6 }, new[] { 0.4, 0.4, n } }, 0.4, 0.3, 0.3);
        var none = Table(3, new[] { "a", "b", "c" }, new double[0][], 0.4, 0.3, 0.3);
        none.PairNames.Clear();
        var rows = TournamentOverview.Pairwise(new[] { same, none });
        Assert.DoesNotContain(rows, r => r.A == r.B);
        Assert.Single(rows.Where(r => r.A == "a" && r.B == "b"));
    }
}
