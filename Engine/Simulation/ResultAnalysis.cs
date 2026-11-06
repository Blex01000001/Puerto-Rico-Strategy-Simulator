namespace PuertoRico.Engine.Simulation;

public sealed class StrategyAnalysis
{
    public string SeatId { get; set; } = "";
    public string Strategy { get; set; } = "";
    public int Games { get; set; }
    public double WinShare { get; set; }
    /// <summary>Half-width of the 95% confidence interval of <see cref="WinShare"/>.</summary>
    public double WinShareCi95 { get; set; }
    public double AvgScore { get; set; }
    public double StdScore { get; set; }
    public int P10 { get; set; }
    public int P50 { get; set; }
    public int P90 { get; set; }
    public double AvgChips { get; set; }
    public double AvgBuildingPoints { get; set; }
    public double AvgBonusPoints { get; set; }
    public double AvgTiebreak { get; set; }
    public double MeanRank { get; set; }
    /// <summary>Share of games finished with rank &lt;= players/2 (top 2 of 4 players; first place only with 3 players).</summary>
    public double TopHalfShare { get; set; }
    public double LastPlaceShare { get; set; }

    // ---- need the per-player building data (files from older versions leave these at 0) ----
    public double AvgBuildings { get; set; }
    public double AvgLargeBuildings { get; set; }
    public double AvgShipments { get; set; }
    public double AvgCoins { get; set; }
    /// <summary>Share of this strategy's games in which it owned a Harbor, and the mean round it was bought.</summary>
    public double HarborShare { get; set; }
    public double AvgHarborRound { get; set; }
    /// <summary>Mean tiles at the end: corn, indigo, sugar, tobacco, coffee, quarry.</summary>
    public List<double> AvgTiles { get; set; } = new();
}

/// <summary>Ownership and results per building over all players of all strategies.</summary>
public sealed class BuildingStat
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    /// <summary>Per strategy (same order as <see cref="ResultAnalysis.Strategies"/>): share of its games owning this building.</summary>
    public List<double> OwnedShare { get; set; } = new();
    public int OwnerPlayers { get; set; }
    /// <summary>Win share (ties split) of players who owned the building at the end, and of those who did not.</summary>
    public double WinShareOwned { get; set; }
    public double WinShareNotOwned { get; set; }
    /// <summary>Mean round in which the building was bought.</summary>
    public double AvgBuiltRound { get; set; }
}

/// <summary>Counts per score bin, one series per strategy (in the same order as <see cref="ResultAnalysis.Strategies"/>).</summary>
public sealed class ScoreHistogram
{
    public int BinWidth { get; set; } = 2;
    public int MinScore { get; set; }
    public int BinCount { get; set; }
    /// <summary>Series[strategy][bin] = fraction of that strategy's games falling into the bin.</summary>
    public List<List<double>> Series { get; set; } = new();
}

/// <summary>
/// Statistics for the Dashboard computed from a <see cref="SimulationResult"/> (UI-free so it is testable and reusable).
/// Anything that needs individual games is empty when the file has no per-game records.
/// </summary>
public sealed class ResultAnalysis
{
    public bool HasGameRecords { get; set; }
    public int GamesCompleted { get; set; }
    public List<StrategyAnalysis> Strategies { get; set; } = new();
    public ScoreHistogram Scores { get; set; } = new();
    /// <summary>Index = rounds played, value = number of games.</summary>
    public List<int> RoundCounts { get; set; } = new();
    public double AvgRounds { get; set; }
    public double AvgDecisions { get; set; }
    public List<TableSeatSummary> TableSeats { get; set; } = new();
    public Dictionary<string, int> EndReasons { get; set; } = new();
    /// <summary>Pairwise[i][j] = share of games (not tied on rank) where strategy i ranked above strategy j; NaN on the diagonal.</summary>
    public List<List<double>> Pairwise { get; set; } = new();
    /// <summary>True when every player record carries building data (files written by this version or newer).</summary>
    public bool HasBuildingRecords { get; set; }
    public List<BuildingStat> Buildings { get; set; } = new();

    public static ResultAnalysis From(SimulationResult result)
    {
        var a = new ResultAnalysis
        {
            GamesCompleted = result.GamesCompleted,
            HasGameRecords = result.Games.Count > 0,
            TableSeats = result.TableSeats,
            EndReasons = result.EndReasons,
        };

        var seats = result.Config.Seats;
        if (!a.HasGameRecords)
        {
            foreach (var s in result.Summary)
                a.Strategies.Add(new StrategyAnalysis
                {
                    SeatId = s.SeatId,
                    Strategy = s.Strategy,
                    Games = s.Games,
                    WinShare = s.WinShare,
                    WinShareCi95 = Ci(s.WinShare, s.Games),
                    AvgScore = s.AvgScore,
                    StdScore = s.StdScore,
                });
            return a;
        }

        var games = result.Games;
        a.AvgRounds = games.Average(g => (double)g.Rounds);
        a.AvgDecisions = games.Average(g => (double)g.Decisions);
        int maxRounds = games.Max(g => g.Rounds);
        a.RoundCounts = new int[maxRounds + 1].ToList();
        foreach (var g in games) a.RoundCounts[g.Rounds]++;

        var scoresById = seats.ToDictionary(s => s.Id, _ => new List<int>());
        foreach (var seat in seats)
        {
            var rows = new List<(GameRecord g, PlayerRecord p)>();
            foreach (var g in games)
                foreach (var p in g.Players)
                    if (p.SeatId == seat.Id) rows.Add((g, p));
            int n = rows.Count;
            var vp = rows.Select(r => r.p.Vp).OrderBy(v => v).ToList();
            scoresById[seat.Id] = vp;
            double share = n == 0 ? 0 : rows.Sum(r => r.g.Winners.Contains(r.p.Seat) ? 1.0 / r.g.Winners.Count : 0.0) / n;
            double avg = n == 0 ? 0 : vp.Average();
            int players = result.Config.Players;
            a.Strategies.Add(new StrategyAnalysis
            {
                SeatId = seat.Id,
                Strategy = seat.Strategy,
                Games = n,
                WinShare = share,
                WinShareCi95 = Ci(share, n),
                AvgScore = avg,
                StdScore = n == 0 ? 0 : Math.Sqrt(vp.Average(v => Math.Pow(v - avg, 2))),
                P10 = Percentile(vp, 0.10),
                P50 = Percentile(vp, 0.50),
                P90 = Percentile(vp, 0.90),
                AvgChips = n == 0 ? 0 : rows.Average(r => (double)r.p.Chips),
                AvgBuildingPoints = n == 0 ? 0 : rows.Average(r => (double)r.p.BuildingPoints),
                AvgBonusPoints = n == 0 ? 0 : rows.Average(r => (double)r.p.BonusPoints),
                AvgTiebreak = n == 0 ? 0 : rows.Average(r => (double)r.p.Tiebreak),
                MeanRank = n == 0 ? 0 : rows.Average(r => (double)r.p.Rank),
                TopHalfShare = n == 0 ? 0 : rows.Count(r => r.p.Rank <= players / 2) / (double)n,
                LastPlaceShare = n == 0 ? 0 : rows.Count(r => r.p.Rank == players) / (double)n,
            });
        }

        a.HasBuildingRecords = games.All(g => g.Players.All(p => p.Buildings != null && p.BuiltRounds != null));
        if (a.HasBuildingRecords) AddBuildingStats(a, games, seats);

        // score histogram
        var all = scoresById.Values.SelectMany(v => v).ToList();
        int min = all.Count == 0 ? 0 : all.Min();
        int max = all.Count == 0 ? 0 : all.Max();
        var hist = new ScoreHistogram { BinWidth = 2, MinScore = min - (min % 2 + 2) % 2 };
        hist.BinCount = (max - hist.MinScore) / hist.BinWidth + 1;
        foreach (var seat in seats)
        {
            var counts = new double[hist.BinCount];
            var vp = scoresById[seat.Id];
            foreach (int v in vp) counts[(v - hist.MinScore) / hist.BinWidth]++;
            hist.Series.Add(counts.Select(c => vp.Count == 0 ? 0 : c / vp.Count).ToList());
        }
        a.Scores = hist;

        // pairwise ranking
        for (int i = 0; i < seats.Count; i++)
        {
            var row = new List<double>();
            for (int j = 0; j < seats.Count; j++)
            {
                if (i == j) { row.Add(double.NaN); continue; }
                int wins = 0, losses = 0;
                foreach (var g in games)
                {
                    var pi = g.Players.FirstOrDefault(p => p.SeatId == seats[i].Id);
                    var pj = g.Players.FirstOrDefault(p => p.SeatId == seats[j].Id);
                    if (pi == null || pj == null) continue;
                    if (pi.Rank < pj.Rank) wins++;
                    else if (pi.Rank > pj.Rank) losses++;
                }
                row.Add(wins + losses == 0 ? double.NaN : wins / (double)(wins + losses));
            }
            a.Pairwise.Add(row);
        }
        return a;
    }

    private static void AddBuildingStats(ResultAnalysis a, List<GameRecord> games, List<SeatConfig> seats)
    {
        for (int k = 0; k < seats.Count; k++)
        {
            var rows = new List<PlayerRecord>();
            foreach (var g in games) rows.AddRange(g.Players.Where(p => p.SeatId == seats[k].Id));
            int n = Math.Max(1, rows.Count);
            var st = a.Strategies[k];
            st.AvgBuildings = rows.Average(p => (double)p.Buildings!.Count);
            st.AvgLargeBuildings = rows.Average(p => (double)p.Buildings!.Count(id => Game.Buildings.All[id].Large));
            st.AvgShipments = rows.Average(p => (double)p.Shipments);
            st.AvgCoins = rows.Average(p => (double)p.Coins);
            int harbor = (int)Game.BuildingId.Harbor;
            var harborRows = rows.Where(p => p.Buildings!.Contains(harbor)).ToList();
            st.HarborShare = harborRows.Count / (double)n;
            st.AvgHarborRound = harborRows.Count == 0 ? 0 : harborRows.Average(p => (double)p.BuiltRounds![p.Buildings!.IndexOf(harbor)]);
            int tileKinds = Game.GameConstants.TileTypes;
            st.AvgTiles = Enumerable.Range(0, tileKinds).Select(t => rows.Average(p => p.Tiles != null && p.Tiles.Count > t ? (double)p.Tiles[t] : 0)).ToList();
        }

        for (int b = 0; b < Game.GameConstants.BuildingCount; b++)
        {
            var stat = new BuildingStat { Id = b, Name = Game.Buildings.All[b].Name };
            double ownedWin = 0, otherWin = 0; int owners = 0, others = 0; double roundSum = 0;
            var ownedByStrategy = new int[seats.Count];
            var gamesByStrategy = new int[seats.Count];
            foreach (var g in games)
            {
                foreach (var p in g.Players)
                {
                    int k = seats.FindIndex(s => s.Id == p.SeatId);
                    if (k >= 0) gamesByStrategy[k]++;
                    double credit = g.Winners.Contains(p.Seat) ? 1.0 / g.Winners.Count : 0;
                    int at = p.Buildings!.IndexOf(b);
                    if (at >= 0)
                    {
                        owners++; ownedWin += credit; roundSum += p.BuiltRounds![at];
                        if (k >= 0) ownedByStrategy[k]++;
                    }
                    else { others++; otherWin += credit; }
                }
            }
            stat.OwnerPlayers = owners;
            stat.WinShareOwned = owners == 0 ? 0 : ownedWin / owners;
            stat.WinShareNotOwned = others == 0 ? 0 : otherWin / others;
            stat.AvgBuiltRound = owners == 0 ? 0 : roundSum / owners;
            stat.OwnedShare = Enumerable.Range(0, seats.Count).Select(k => gamesByStrategy[k] == 0 ? 0 : ownedByStrategy[k] / (double)gamesByStrategy[k]).ToList();
            a.Buildings.Add(stat);
        }
    }

    public static double Ci(double p, int n) => n <= 0 ? 0 : 1.96 * Math.Sqrt(Math.Max(p * (1 - p), 0) / n);

    private static int Percentile(List<int> sorted, double q) =>
        sorted.Count == 0 ? 0 : sorted[(int)(q * (sorted.Count - 1))];
}
