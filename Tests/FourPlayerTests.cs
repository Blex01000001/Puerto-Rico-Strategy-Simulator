using System.Text.Json;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using Xunit;
using static PuertoRico.Tests.Sc;

namespace PuertoRico.Tests;

// rules.md section 7 (4-player game)
public class FourPlayerTests
{
    private static GameState New4(ulong seed = 1) => Setup.NewGame(seed, players: 4);

    [Fact]
    public void Setup_Matches_The_4_Player_Table()
    {
        var s = New4();
        Assert.Equal(4, s.PlayerCount);
        Assert.Equal(new[] { 3, 3, 3, 3 }, s.Coins.Take(4));
        Assert.Equal(75, s.BankColonists);
        Assert.Equal(4, s.ShipColonists);
        Assert.Equal(79, s.ColonistTotal);
        Assert.Equal(100, s.VpSupply);
        Assert.Equal(new[] { 5, 6, 7 }, s.ShipCap);
        Assert.Equal(5, s.FaceUp.Sum());
        Assert.Equal(46, s.Deck.Sum() + s.FaceUp.Sum());
        Assert.Equal(new[] { 8, 10, 11, 9, 8 }, GameConstants.DeckStart(4));
        Assert.Equal(7, s.RoleCount);
        Assert.Equal(50, s.GoodsSupply.Sum());
        Assert.Equal(8, s.QuarrySupply);
        Assert.Null(Invariants.Check(s));
    }

    [Fact]
    public void Starting_Plantations_Are_Indigo_Indigo_Corn_Corn()
    {
        var s = New4();
        Assert.Equal(1, s.Tiles[0 * 6 + (int)Good.Indigo]);
        Assert.Equal(1, s.Tiles[1 * 6 + (int)Good.Indigo]);
        Assert.Equal(1, s.Tiles[2 * 6 + (int)Good.Corn]);
        Assert.Equal(1, s.Tiles[3 * 6 + (int)Good.Corn]);
    }

    [Fact]
    public void Prospector_Gives_One_Coin_And_Ends_Immediately()
    {
        var s = New4();
        Start(s, 0, Role.Prospector);
        Assert.Equal(4, s.Coins[0]);
        Assert.Equal(Phase.ChooseRole, s.Phase);
        Assert.Equal(1, s.Actor); // the next player chooses
        Assert.Equal(1, s.ChosenCount);
    }

    [Fact]
    public void Prospector_Collects_Role_Coins_Too_And_Is_Not_Offered_In_3_Player_Games()
    {
        var s = New4();
        s.RoleCoins[(int)Role.Prospector] = 2;
        Start(s, 0, Role.Prospector);
        Assert.Equal(3 + 2 + 1, s.Coins[0]);

        var three = New();
        Assert.False(Has(Legal(three), ActionType.ChooseRole, (int)Role.Prospector));
        Assert.Equal(6, Legal(three).Count);
        Assert.Equal(7, Legal(New4()).Count);
    }

    [Fact]
    public void Four_Players_Choose_Then_Three_Unchosen_Roles_Get_Coins()
    {
        var s = New4();
        Start(s, 0, Role.Prospector);
        Do(s, A(ActionType.ChooseRole, (int)Role.Craftsman));
        Do(s, A(ActionType.ChooseRole, (int)Role.Trader));
        Do(s, A(ActionType.ChooseRole, (int)Role.Captain));
        Assert.Equal(2, s.Round);
        Assert.Equal(1, s.Governor);
        Assert.Equal(1, s.RoleCoins[(int)Role.Settler]);
        Assert.Equal(1, s.RoleCoins[(int)Role.Mayor]);
        Assert.Equal(1, s.RoleCoins[(int)Role.Builder]);
        Assert.Equal(0, s.RoleCoins[(int)Role.Prospector]);
        Assert.Equal(3, s.RoleCoins.Count(c => c == 1));
    }

    [Fact]
    public void Settler_Flips_Five_New_Tiles()
    {
        var s = New4();
        Start(s, 0, Role.Settler);
        PassUntil(s, Phase.Settler);
        Assert.Equal(5, s.Discard.Sum());
        Assert.Equal(5, s.FaceUp.Sum());
    }

    [Fact]
    public void Mayor_Refill_Floor_Is_Four_And_Ship_Goes_Round_All_Four()
    {
        var s = New4();
        s.ShipColonists = 0;
        Start(s, 0, Role.Mayor);
        while (s.Phase == Phase.Mayor) Do(s, Legal(s)[0]);
        Assert.Equal(4, s.ShipColonists);

        var t = New4();
        t.ShipColonists = 6;
        Start(t, 2, Role.Mayor); // privilege 1 + ship 6 spread from seat 2
        Assert.Equal(7, Enumerable.Range(0, 4).Sum(p => t.ColonistsOnBoard(p)));
    }

    [Fact]
    public void Colonist_Shortage_Uses_The_Player_Count_Floor()
    {
        var s = New4();
        s.ShipColonists = 0;
        s.BankColonists = 4; // privilege leaves 3 < 4
        Start(s, 0, Role.Mayor);
        while (s.Phase == Phase.Mayor) Do(s, Legal(s)[0]);
        Assert.True((s.EndFlags & EndFlags.ColonistsShort) != 0);
    }

    [Fact]
    public void Random_4_Player_Games_Keep_Invariants_And_Terminate()
    {
        var rng = new Random(8);
        var reasons = new HashSet<EndFlags>();
        for (int game = 0; game < 120; game++)
        {
            var s = Setup.NewGame((ulong)game + 500, players: 4);
            var legal = new List<GameAction>();
            int steps = 0;
            while (!s.IsOver)
            {
                Rules.GetLegalActions(s, legal);
                Assert.NotEmpty(legal);
                Rules.Apply(s, legal[rng.Next(legal.Count)]);
                var err = Invariants.Check(s);
                Assert.True(err == null, $"game {game} step {steps}: {err}");
                Assert.True(++steps < 30000);
            }
            reasons.Add(s.EndFlags);
            var score = Scoring.Score(s);
            Assert.Equal(4, score.Players.Length);
            Assert.NotEmpty(score.Winners);
        }
        Assert.NotEmpty(reasons);
    }

    [Fact]
    public void Clone_Of_A_4_Player_State_Is_Independent()
    {
        var a = New4(9);
        var b = a.Clone();
        b.Coins[3] = 50;
        b.ShipCap[0] = 99;
        Assert.Equal(3, a.Coins[3]);
        Assert.Equal(5, a.ShipCap[0]);
        Assert.Equal(4, b.PlayerCount);
    }

    [Fact]
    public void Batch_Runs_4_Player_Games_With_Rotation_And_Is_Reproducible()
    {
        var cfg = new SimulationConfig
        {
            Players = 4,
            Games = 80,
            Seed = 5,
            Seats = new[] { "A", "B", "C", "D" }.Select(id => new SeatConfig { Id = id, Strategy = "random" }).ToList(),
        };
        cfg.Validate();
        var one = BatchSimulator.Run(cfg, new BatchOptions(), CancellationToken.None);
        cfg.Parallelism.MaxDegree = 1;
        var two = BatchSimulator.Run(cfg, new BatchOptions(), CancellationToken.None);
        string J(object o) => JsonSerializer.Serialize(o, SimulationConfig.JsonOptions);
        Assert.Equal(J(one.Games), J(two.Games));
        Assert.Equal(4, one.TableSeats.Count);
        Assert.All(one.Games, g => Assert.Equal(4, g.Players.Count));
        // rotation: every strategy slot sits at every seat
        var seen = new Dictionary<string, HashSet<int>>();
        foreach (var g in one.Games.Take(8))
            foreach (var p in g.Players) (seen.TryGetValue(p.SeatId, out var set) ? set : seen[p.SeatId] = new()).Add(p.Seat);
        Assert.All(seen.Values, v => Assert.Equal(4, v.Count));
    }

    [Fact]
    public void Config_Rejects_Mismatched_Seat_Count_And_5_Players()
    {
        var cfg = new SimulationConfig { Players = 4 }; // 3 seats by default
        Assert.Throws<InvalidDataException>(() => cfg.Validate());
        var five = new SimulationConfig { Players = 5 };
        Assert.Throws<InvalidDataException>(() => five.Validate());
    }

    [Theory]
    [InlineData("corn-shipper")]
    [InlineData("corn-to-premium")]
    [InlineData("harbor-rush")]
    public void Heuristic_Strategies_Play_4_Player_Games(string strategy)
    {
        var cfg = new SimulationConfig
        {
            Players = 4,
            Games = 40,
            Seed = 21,
            Seats = new[] { "A", "B", "C", "D" }.Select((id, i) => new SeatConfig { Id = id, Strategy = i == 0 ? strategy : "random" }).ToList(),
        };
        var r = BatchSimulator.Run(cfg, new BatchOptions(), CancellationToken.None);
        Assert.Equal(40, r.GamesCompleted);
        Assert.True(r.Summary[0].WinShare > 0.5, $"{strategy}: {r.Summary[0].WinShare}");
    }
}
