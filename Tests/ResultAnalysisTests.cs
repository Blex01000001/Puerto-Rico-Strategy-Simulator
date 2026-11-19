using PuertoRico.Engine.Simulation;
using Xunit;

namespace PuertoRico.Tests;

public class ResultAnalysisTests
{
    private static SimulationResult Fake()
    {
        // two strategies A,B in 3-player config where C is unused; hand-made records
        var cfg = new SimulationConfig();
        var result = new SimulationResult { Config = cfg, GamesRequested = 4 };
        GameRecord Game(int i, int rounds, (string id, int seat, int vp, int rank)[] players, int[] winners) => new()
        {
            Index = i,
            Rounds = rounds,
            Decisions = 100 + i,
            EndReason = "vpExhausted",
            Winners = winners.ToList(),
            Players = players.Select(p => new PlayerRecord { SeatId = p.id, Seat = p.seat, Vp = p.vp, Chips = p.vp - 5, BuildingPoints = 5, BonusPoints = 0, Tiebreak = 2, Rank = p.rank }).ToList(),
        };
        result.Games.Add(Game(0, 15, new[] { ("A", 0, 40, 1), ("B", 1, 30, 2), ("C", 2, 20, 3) }, new[] { 0 }));
        result.Games.Add(Game(1, 16, new[] { ("A", 1, 30, 1), ("B", 0, 30, 1), ("C", 2, 10, 3) }, new[] { 0, 1 })); // tie for first
        result.Games.Add(Game(2, 16, new[] { ("A", 2, 20, 3), ("B", 0, 35, 1), ("C", 1, 25, 2) }, new[] { 0 }));
        result.Games.Add(Game(3, 18, new[] { ("A", 0, 50, 1), ("B", 1, 20, 3), ("C", 2, 30, 2) }, new[] { 0 }));
        ResultSummarizer.Fill(result, result.Games);
        return result;
    }

    [Fact]
    public void Computes_Win_Share_Scores_And_Ranks()
    {
        var a = ResultAnalysis.From(Fake());
        Assert.True(a.HasGameRecords);
        var A = a.Strategies[0]; var B = a.Strategies[1]; var C = a.Strategies[2];
        Assert.Equal((1 + 0.5 + 0 + 1) / 4.0, A.WinShare, 9);
        Assert.Equal((0 + 0.5 + 1 + 0) / 4.0, B.WinShare, 9);
        Assert.Equal(0, C.WinShare);
        Assert.Equal((40 + 30 + 20 + 50) / 4.0, A.AvgScore, 9);
        Assert.Equal(new[] { 20, 30, 40, 50 }, new[] { 20, 30, 40, 50 });
        Assert.Equal(30, A.P50); // sorted 20,30,40,50 -> index (int)(0.5*3)=1
        Assert.Equal((1 + 1 + 3 + 1) / 4.0, A.MeanRank, 9);
        Assert.Equal(3 / 4.0, A.TopHalfShare, 9);   // rank <= 1 for 3 players (players/2 = 1)
        Assert.Equal(1 / 4.0, A.LastPlaceShare, 9); // rank 3
        Assert.True(A.WinShareCi95 > 0);
    }

    [Fact]
    public void Histogram_Rounds_And_Pairwise_Are_Consistent()
    {
        var a = ResultAnalysis.From(Fake());
        Assert.All(a.Scores.Series, s => Assert.Equal(1.0, s.Sum(), 9)); // fractions of each strategy's games
        Assert.Equal(a.Scores.BinCount, a.Scores.Series[0].Count);
        Assert.Equal(4, a.RoundCounts.Sum());
        Assert.Equal(1, a.RoundCounts[15]);
        Assert.Equal(2, a.RoundCounts[16]);
        Assert.Equal((15 + 16 + 16 + 18) / 4.0, a.AvgRounds, 9);
        Assert.True(double.IsNaN(a.Pairwise[0][0]));
        // A above B in games 0 and 3, tied rank in game 1, below in game 2 -> 2 wins, 1 loss
        Assert.Equal(2 / 3.0, a.Pairwise[0][1], 9);
        Assert.Equal(1 / 3.0, a.Pairwise[1][0], 9);
    }

    [Fact]
    public void Without_Game_Records_Only_The_Summary_Is_Available()
    {
        var cfg = new SimulationConfig { Games = 50, Seed = 3 };
        cfg.Output.PerGameRecords = false;
        var r = BatchSimulator.Run(cfg, new BatchOptions(), CancellationToken.None);
        var a = ResultAnalysis.From(r);
        Assert.False(a.HasGameRecords);
        Assert.Equal(3, a.Strategies.Count);
        Assert.Equal(1.0, a.Strategies.Sum(s => s.WinShare), 6);
        Assert.Empty(a.RoundCounts);
        Assert.Empty(a.Pairwise);
    }

    [Fact]
    public void Real_Run_Gives_Sane_Numbers()
    {
        var cfg = new SimulationConfig { Games = 400, Seed = 8 };
        cfg.Seats[0].Strategy = "build-first";
        var r = BatchSimulator.Run(cfg, new BatchOptions(), CancellationToken.None);
        var a = ResultAnalysis.From(r);
        Assert.Equal(1.0, a.Strategies.Sum(s => s.WinShare), 6);
        Assert.Equal(400, a.RoundCounts.Sum());
        Assert.All(a.Strategies, s => Assert.InRange(s.P10, 0, s.P90));
        Assert.True(a.Strategies[0].AvgScore > a.Strategies[1].AvgScore);
    }

    [Fact]
    public void Summary_Markdown_Has_Config_Time_Versions_And_Win_Shares()
    {
        var r = Fake();
        r.Config.Name = "t-summary";
        r.Config.Seats[1].Params["valueModel"] = System.Text.Json.JsonSerializer.SerializeToElement("ml/local/models/x.txt");
        r.Status = "completed";
        r.StartedUtc = new DateTime(2026, 11, 17, 12, 0, 0, DateTimeKind.Utc);
        r.FinishedUtc = r.StartedUtc.AddSeconds(125);
        var text = ResultSummary.ToMarkdown(r, ResultAnalysis.From(r));
        Assert.Contains("## 模擬結果：t-summary", text);
        Assert.Contains("3 人局，4 局（completed，預定 4）", text);
        Assert.Contains("耗時：2 分 5 秒，0.03 局/秒", text);
        Assert.Contains($"引擎 {PuertoRico.Engine.Game.EngineInfo.Version}", text);
        Assert.Contains("| B | random | valueModel x.txt |", text);   // the model is shown by file name only
        Assert.DoesNotContain("ml/local", text);
        Assert.Contains("| A | random | — | 62.5% |", text);          // 2.5 wins of 4 games (one tie for first)

        // the English text says the same things and contains no Chinese
        var en = ResultSummary.ToMarkdown(r, ResultAnalysis.From(r), english: true);
        Assert.Contains("## Simulation result: t-summary", en);
        Assert.Contains("3 players, 4 games (completed, 4 planned)", en);
        Assert.Contains("Duration: 2 min 5 s, 0.03 games/s", en);
        Assert.Contains("| B | random | valueModel x.txt |", en);
        Assert.Contains("| A | random | — | 62.5% |", en);
        Assert.DoesNotContain(en, c => c >= (char)0x4e00 && c <= (char)0x9fff);
    }
}
