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
