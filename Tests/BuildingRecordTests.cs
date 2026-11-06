using System.Text.Json;
using PuertoRico.Engine.Events;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using Xunit;

namespace PuertoRico.Tests;

// per-player building list and key statistics in the result file
public class BuildingRecordTests
{
    private static SimulationConfig Cfg(int players = 3) => new()
    {
        Players = players,
        Seed = 77,
        Seats = Enumerable.Range(0, players)
            .Select(i => new SeatConfig { Id = "ABCD"[i].ToString(), Strategy = i == 0 ? "harbor-rush" : i == 1 ? "build-first" : "corn-shipper" }).ToList(),
    };

    [Theory]
    [InlineData(3)]
    [InlineData(4)]
    public void Records_Are_Consistent_With_The_Final_Score(int players)
    {
        var cfg = Cfg(players);
        for (int game = 0; game < 25; game++)
        {
            var rec = GameRunner.Play(cfg, game);
            foreach (var p in rec.Players)
            {
                Assert.NotNull(p.Buildings);
                Assert.Equal(p.Buildings!.Count, p.BuiltRounds!.Count);
                Assert.Equal(p.Buildings.Distinct().Count(), p.Buildings.Count);                       // one of each building
                Assert.Equal(p.BuildingPoints, p.Buildings.Sum(id => Buildings.Vp[id]));                // base VP of what it owns
                Assert.InRange(p.Buildings.Sum(id => Buildings.Spaces[id]), 0, GameConstants.CitySpaces);
                Assert.Equal(p.BuiltRounds.OrderBy(r => r), p.BuiltRounds);                             // purchase order = round order
                Assert.All(p.BuiltRounds, r => Assert.InRange(r, 1, rec.Rounds));
                Assert.Equal(GameConstants.TileTypes, p.Tiles!.Count);
                Assert.InRange(p.Tiles.Sum(), 1, GameConstants.MaxTiles);
                Assert.True(p.Coins >= 0 && p.Shipments >= 0);
            }
        }
    }

    [Fact]
    public void Counts_Match_The_Decision_Log()
    {
        var cfg = Cfg();
        var sink = new ListEventSink();
        var rec = GameRunner.Play(cfg, 5, sink);
        foreach (var p in rec.Players)
        {
            int builds = sink.Events.Count(e => e.Seat == p.Seat && e.Action.StartsWith("Build("));
            int ships = sink.Events.Count(e => e.Seat == p.Seat && (e.Action.StartsWith("LoadShip(") || e.Action.StartsWith("LoadWharf(")));
            Assert.Equal(builds, p.Buildings!.Count);
            Assert.Equal(ships, p.Shipments);
        }
    }

    [Fact]
    public void Harbor_Rush_Records_An_Early_Harbor()
    {
        var cfg = Cfg();
        int withHarbor = 0, n = 40;
        for (int game = 0; game < n; game++)
        {
            var mine = GameRunner.Play(cfg, game).Players.First(p => p.SeatId == "A");
            int at = mine.Buildings!.IndexOf((int)BuildingId.Harbor);
            if (at >= 0) { withHarbor++; Assert.InRange(mine.BuiltRounds![at], 1, 10); }
        }
        Assert.True(withHarbor >= n * 0.9, $"{withHarbor}/{n}");
    }

    [Fact]
    public void Result_File_Round_Trips_The_New_Fields_And_Reads_Old_Files()
    {
        var rec = GameRunner.Play(Cfg(), 1);
        var json = JsonSerializer.Serialize(rec, SimulationConfig.JsonOptions);
        var back = JsonSerializer.Deserialize<GameRecord>(json, SimulationConfig.JsonOptions)!;
        Assert.Equal(rec.Players[0].Buildings, back.Players[0].Buildings);
        Assert.Equal(rec.Players[1].Shipments, back.Players[1].Shipments);

        const string old = "{\"index\":0,\"seed\":1,\"rounds\":10,\"decisions\":5,\"endReason\":\"vpExhausted\",\"players\":[{\"seat\":0,\"seatId\":\"A\",\"vp\":30,\"chips\":20,\"buildingPoints\":10,\"bonusPoints\":0,\"tiebreak\":3,\"rank\":1}],\"winners\":[0]}";
        var oldRec = JsonSerializer.Deserialize<GameRecord>(old, SimulationConfig.JsonOptions)!;
        Assert.Null(oldRec.Players[0].Buildings);
        Assert.Equal(0, oldRec.Players[0].Shipments);
    }

    [Fact]
    public void Resume_Refuses_A_File_Without_Building_Data()
    {
        var cfg = new SimulationConfig { Games = 5, Seed = 3 };
        var oldResult = new SimulationResult { Config = cfg, GamesCompleted = 1 };
        oldResult.Games.Add(new GameRecord { Index = 0, Players = new List<PlayerRecord> { new() { SeatId = "A" } } });
        Assert.Throws<InvalidDataException>(() => BatchSimulator.Run(cfg, new BatchOptions { ResumeFrom = oldResult }, CancellationToken.None));
    }

    [Fact]
    public void Analysis_Computes_Harbor_And_Building_Statistics()
    {
        var cfg = new SimulationConfig();
        var result = new SimulationResult { Config = cfg, GamesRequested = 2 };
        int H = (int)BuildingId.Harbor, M = (int)BuildingId.SmallMarket, G = (int)BuildingId.GuildHall;
        PlayerRecord P(string id, int seat, int vp, int rank, int[] ids, int[] rounds, int ships) => new()
        {
            SeatId = id,
            Seat = seat,
            Vp = vp,
            Rank = rank,
            Chips = vp,
            Buildings = ids.ToList(),
            BuiltRounds = rounds.ToList(),
            Tiles = new List<int> { 3, 1, 0, 0, 0, 1 },
            Coins = 2,
            Shipments = ships,
        };
        result.Games.Add(new GameRecord
        {
            Index = 0,
            Rounds = 16,
            Winners = new List<int> { 0 },
            Players = new List<PlayerRecord>
            {
                P("A", 0, 40, 1, new[] { H, M }, new[] { 6, 8 }, 10),
                P("B", 1, 30, 2, new[] { M }, new[] { 5 }, 6),
                P("C", 2, 20, 3, new int[0], new int[0], 2),
            },
        });
        result.Games.Add(new GameRecord
        {
            Index = 1,
            Rounds = 18,
            Winners = new List<int> { 2 },
            Players = new List<PlayerRecord>
            {
                P("A", 1, 25, 3, new[] { M }, new[] { 4 }, 8),
                P("B", 2, 35, 1, new[] { H, G }, new[] { 10, 14 }, 12),
                P("C", 0, 30, 2, new[] { M }, new[] { 7 }, 4),
            },
        });
        ResultSummarizer.Fill(result, result.Games);
        var a = ResultAnalysis.From(result);

        Assert.True(a.HasBuildingRecords);
        var A = a.Strategies[0]; var Bs = a.Strategies[1];
        Assert.Equal(0.5, A.HarborShare, 9);
        Assert.Equal(6, A.AvgHarborRound, 9);
        Assert.Equal(0.5, Bs.HarborShare, 9);
        Assert.Equal(10, Bs.AvgHarborRound, 9);
        Assert.Equal(1.5, A.AvgBuildings, 9);          // A owns 2 buildings in game 0 and 1 in game 1
        Assert.Equal(9.0, A.AvgShipments, 9);
        Assert.Equal(new[] { 3.0, 1, 0, 0, 0, 1 }, A.AvgTiles);

        var harbor = a.Buildings[H];
        Assert.Equal(2, harbor.OwnerPlayers);
        Assert.Equal(1.0, harbor.WinShareOwned, 9);          // both Harbor owners won their game
        Assert.Equal(0.0, harbor.WinShareNotOwned, 9);
        Assert.Equal(8.0, harbor.AvgBuiltRound, 9);          // (6 + 10) / 2
        var market = a.Buildings[M];
        Assert.Equal(4, market.OwnerPlayers);
        Assert.Equal(1.0, market.OwnedShare[0], 9);          // A owned a market in both games
        Assert.Equal(1 / 4.0, market.WinShareOwned, 9);      // 4 market owners; only A in game 0 won
    }

    [Fact]
    public void Old_Files_Still_Analyse_Without_Building_Data()
    {
        var cfg = new SimulationConfig();
        var result = new SimulationResult { Config = cfg };
        result.Games.Add(new GameRecord
        {
            Index = 0,
            Rounds = 15,
            Winners = new List<int> { 0 },
            Players = new[] { "A", "B", "C" }.Select((id, i) => new PlayerRecord { SeatId = id, Seat = i, Vp = 30 - i, Rank = i + 1 }).ToList(),
        });
        ResultSummarizer.Fill(result, result.Games);
        var a = ResultAnalysis.From(result);
        Assert.False(a.HasBuildingRecords);
        Assert.Empty(a.Buildings);
        Assert.Equal(0, a.Strategies[0].AvgBuildings);
    }
}
