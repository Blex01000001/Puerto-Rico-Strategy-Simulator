using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Simulation;

public sealed class PlayerRecord
{
    /// <summary>Table seat (0..2 = Player 1..3).</summary>
    public int Seat { get; set; }
    /// <summary>Id of the config seat (strategy slot) that sat here.</summary>
    public string SeatId { get; set; } = "";
    public int Vp { get; set; }
    public int Chips { get; set; }
    public int BuildingPoints { get; set; }
    public int BonusPoints { get; set; }
    public int Tiebreak { get; set; }
    public int Rank { get; set; }
}

public sealed class GameRecord
{
    public int Index { get; set; }
    public ulong Seed { get; set; }
    public int Rounds { get; set; }
    public int Decisions { get; set; }
    public string EndReason { get; set; } = "";
    public List<PlayerRecord> Players { get; set; } = new();
    /// <summary>Winning table seats (more than one on a full tie).</summary>
    public List<int> Winners { get; set; } = new();
}

public sealed class SeatSummary
{
    public string SeatId { get; set; } = "";
    public string Strategy { get; set; } = "";
    public int Games { get; set; }
    public int Wins { get; set; }
    /// <summary>Fraction of games won, counting 1/n for an n-way tie.</summary>
    public double WinShare { get; set; }
    public double AvgScore { get; set; }
    public double StdScore { get; set; }
}

public sealed class TableSeatSummary
{
    public int Seat { get; set; }
    public int Games { get; set; }
    public double WinShare { get; set; }
    public double AvgScore { get; set; }
}

public sealed class SimulationResult
{
    public int SchemaVersion { get; set; } = 1;
    public string EngineVersion { get; set; } = EngineInfo.Version;
    public string RulesVersion { get; set; } = EngineInfo.RulesVersion;
    /// <summary>running | completed | cancelled</summary>
    public string Status { get; set; } = "running";
    public DateTime StartedUtc { get; set; }
    public DateTime? FinishedUtc { get; set; }
    public int GamesRequested { get; set; }
    public int GamesCompleted { get; set; }
    public SimulationConfig Config { get; set; } = new();
    /// <summary>Per strategy slot (the figure to compare strategies by).</summary>
    public List<SeatSummary> Summary { get; set; } = new();
    /// <summary>Per table seat (shows the seat advantage).</summary>
    public List<TableSeatSummary> TableSeats { get; set; } = new();
    public Dictionary<string, int> EndReasons { get; set; } = new();
    public List<GameRecord> Games { get; set; } = new();
}

public static class ResultSummarizer
{
    public static void Fill(SimulationResult result, IReadOnlyList<GameRecord> records)
    {
        result.GamesCompleted = records.Count;
        result.Summary = result.Config.Seats.Select(cs =>
        {
            var rows = records.SelectMany(g => g.Players.Where(p => p.SeatId == cs.Id).Select(p => (g, p))).ToList();
            double share = rows.Sum(r => r.g.Winners.Contains(r.p.Seat) ? 1.0 / r.g.Winners.Count : 0.0);
            double avg = rows.Count == 0 ? 0 : rows.Average(r => (double)r.p.Vp);
            double std = rows.Count == 0 ? 0 : Math.Sqrt(rows.Average(r => Math.Pow(r.p.Vp - avg, 2)));
            return new SeatSummary
            {
                SeatId = cs.Id,
                Strategy = cs.Strategy,
                Games = rows.Count,
                Wins = rows.Count(r => r.g.Winners.Contains(r.p.Seat)),
                WinShare = rows.Count == 0 ? 0 : share / rows.Count,
                AvgScore = avg,
                StdScore = std,
            };
        }).ToList();

        result.TableSeats = Enumerable.Range(0, GameConstants.Players).Select(seat =>
        {
            var rows = records.Select(g => (g, p: g.Players.First(p => p.Seat == seat))).ToList();
            return new TableSeatSummary
            {
                Seat = seat,
                Games = rows.Count,
                WinShare = rows.Count == 0 ? 0 : rows.Sum(r => r.g.Winners.Contains(seat) ? 1.0 / r.g.Winners.Count : 0.0) / rows.Count,
                AvgScore = rows.Count == 0 ? 0 : rows.Average(r => (double)r.p.Vp),
            };
        }).ToList();

        result.EndReasons = records.GroupBy(g => g.EndReason).OrderBy(g => g.Key, StringComparer.Ordinal)
            .ToDictionary(g => g.Key, g => g.Count());
    }
}
