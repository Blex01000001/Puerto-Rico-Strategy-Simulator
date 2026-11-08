using PuertoRico.Engine.Simulation;
using Xunit;

namespace PuertoRico.Tests;

public class ResultComparisonTests
{
    private static ResultAnalysis Make(params (string strategy, double win, double ci, double score)[] rows)
    {
        var a = new ResultAnalysis();
        int i = 0;
        foreach (var r in rows)
            a.Strategies.Add(new StrategyAnalysis { SeatId = $"s{i++}", Strategy = r.strategy, WinShare = r.win, WinShareCi95 = r.ci, AvgScore = r.score, Games = 1000 });
        return a;
    }

    [Fact]
    public void Matches_strategies_by_name_and_computes_delta()
    {
        var a = Make(("build-first", 0.46, 0.003, 42.5), ("corn-shipper", 0.21, 0.003, 35.1));
        var b = Make(("corn-shipper", 0.25, 0.003, 36.0), ("build-first", 0.36, 0.003, 40.0));
        var rows = ResultComparison.Compare(a, b);
        Assert.Equal(2, rows.Count);
        var build = rows.Single(r => r.Strategy == "build-first");
        Assert.Equal(-0.10, build.DeltaWin, 6);
        Assert.Equal(-2.5, build.DeltaScore, 6);
        Assert.True(build.Significant);
    }

    [Fact]
    public void Difference_inside_interval_is_not_significant()
    {
        var rows = ResultComparison.Compare(Make(("random", 0.25, 0.01, 30)), Make(("random", 0.255, 0.01, 30)));
        Assert.False(rows[0].Significant);
    }

    [Fact]
    public void Repeated_strategy_names_match_by_order_and_missing_side_is_kept()
    {
        var a = Make(("random", 0.3, 0.01, 30), ("random", 0.2, 0.01, 28));
        var b = Make(("random", 0.4, 0.01, 31), ("random", 0.1, 0.01, 27), ("build-first", 0.5, 0.01, 40));
        var rows = ResultComparison.Compare(a, b);
        Assert.Equal(3, rows.Count);
        Assert.Equal(0.1, rows[0].DeltaWin, 6);
        Assert.Equal(-0.1, rows[1].DeltaWin, 6);
        Assert.False(rows[2].HasBoth);
    }
}
