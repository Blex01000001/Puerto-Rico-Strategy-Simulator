using System.Text.Json;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies;
using PuertoRico.Engine.Strategies.RuleBased;
using Xunit;
using static PuertoRico.Tests.Sc;

namespace PuertoRico.Tests;

public class CornShipperTests
{
    private static readonly IReadOnlyDictionary<string, JsonElement> NoParams = new Dictionary<string, JsonElement>();

    private static GameAction Choose(GameState s) => new CornShipperStrategy(NoParams).ChooseAction(s, Legal(s));

    [Fact]
    public void Only_Returns_Legal_Actions_And_Finishes_Games_Against_Random()
    {
        for (int game = 0; game < 150; game++)
        {
            var corn = new CornShipperStrategy(NoParams);
            var rnd1 = new RandomStrategy((ulong)game);
            var rnd2 = new RandomStrategy((ulong)game + 1);
            var s = Setup.NewGame((ulong)game + 5);
            var legal = new List<GameAction>();
            int steps = 0;
            while (!s.IsOver)
            {
                Rules.GetLegalActions(s, legal);
                IStrategy who = s.Actor == game % 3 ? corn : (s.Actor == (game + 1) % 3 ? rnd1 : rnd2);
                var a = who.ChooseAction(s, legal);
                Assert.Contains(a, legal);
                Rules.Apply(s, a);
                Assert.True(++steps < 20000);
            }
        }
    }

    [Fact]
    public void Beats_Two_Random_Players_Most_Of_The_Time()
    {
        var cfg = new SimulationConfig { Games = 300, Seed = 4 };
        cfg.Seats[0].Strategy = "rule-based";
        cfg.Seats[0].Params["profile"] = JsonDocument.Parse("\"corn-shipper\"").RootElement.Clone();
        var r = BatchSimulator.Run(cfg, new BatchOptions(), CancellationToken.None);
        Assert.True(r.Summary[0].WinShare > 0.8, $"win share {r.Summary[0].WinShare}");
    }

    [Fact]
    public void Is_Deterministic()
    {
        var cfg = new SimulationConfig { Seed = 9 };
        cfg.Seats[1].Strategy = "corn-shipper";
        var a = JsonSerializer.Serialize(GameRunner.Play(cfg, 3), SimulationConfig.JsonOptions);
        var b = JsonSerializer.Serialize(GameRunner.Play(cfg, 3), SimulationConfig.JsonOptions);
        Assert.Equal(a, b);
    }

    [Fact]
    public void Settler_Takes_Corn_Over_Other_Plantations()
    {
        var s = New();
        Array.Clear(s.FaceUp);
        s.FaceUp[(int)Good.Coffee] = 2; s.FaceUp[(int)Good.Corn] = 1; s.FaceUp[(int)Good.Sugar] = 1;
        Start(s, 0, Role.Settler);
        Assert.Equal(A(ActionType.TakePlantation, (int)Good.Corn), Choose(s));
    }

    [Fact]
    public void Uses_Hacienda_First()
    {
        var s = New();
        Own(s, 0, BuildingId.Hacienda, 1);
        Start(s, 0, Role.Settler);
        Assert.Equal(ActionType.UseHacienda, Choose(s).Type);
    }

    [Fact]
    public void Mayor_Fills_Corn_Before_Buildings_And_Buildings_Before_Useless_Plants()
    {
        var s = New();
        SetTiles(s, 0, (int)Good.Corn, 1);
        Own(s, 0, BuildingId.Harbor);
        Own(s, 0, BuildingId.SmallSugarMill);
        s.ShipColonists = 1; // seat 0: privilege + 1 = 2 colonists
        Start(s, 0, Role.Mayor);
        var first = Choose(s);
        Assert.Equal(A(ActionType.PlaceColonist, (int)Good.Corn), first);
        Do(s, first);
        Assert.Equal(A(ActionType.PlaceColonist, 6 + (int)BuildingId.Harbor), Choose(s));
    }

    [Fact]
    public void Chooses_Captain_When_Holding_Corn_And_Ships_Are_Empty()
    {
        var s = New();
        SetGoods(s, 0, (int)Good.Corn, 5);
        s.GoodsSupply[(int)Good.Corn] -= 5;
        Assert.Equal(A(ActionType.ChooseRole, (int)Role.Captain), Choose(s));
    }

    [Fact]
    public void Ships_Corn_Where_It_Scores_Most_And_Never_Sells_It_For_Nothing()
    {
        var s = New();
        SetGoods(s, 0, (int)Good.Corn, 9);
        s.GoodsSupply[(int)Good.Corn] -= 9;
        Start(s, 0, Role.Captain);
        Assert.Equal(A(ActionType.LoadShip, (int)Good.Corn, 2), Choose(s)); // capacity 6 = most barrels

        var t = New();
        SetGoods(t, 0, (int)Good.Corn, 2);
        SetGoods(t, 0, (int)Good.Coffee, 1);
        t.GoodsSupply[(int)Good.Corn] -= 2; t.GoodsSupply[(int)Good.Coffee] -= 1;
        Start(t, 0, Role.Trader);
        Assert.Equal(A(ActionType.Sell, (int)Good.Coffee), Choose(t));
    }

    [Fact]
    public void Does_Not_Overspend_On_Cheap_Buildings()
    {
        var s = New();
        s.Coins[0] = 0;
        Start(s, 0, Role.Builder); // the Builder only affords 1-cost buildings, none worth buying
        Assert.Equal(GameAction.Pass, Choose(s));
        var t = New();
        t.Coins[0] = 6;
        Start(t, 0, Role.Builder);
        Assert.Equal(A(ActionType.Build, (int)BuildingId.Hacienda), Choose(t));
    }

    [Fact]
    public void Registry_Builds_The_Strategy_By_Name_And_Rejects_Unknown_Profiles()
    {
        var profile = new Dictionary<string, JsonElement> { ["profile"] = JsonDocument.Parse("\"corn-shipper\"").RootElement.Clone() };
        Assert.IsType<CornShipperStrategy>(StrategyRegistry.Create("rule-based", profile, 1, 0));
        Assert.IsType<CornShipperStrategy>(StrategyRegistry.Create("corn-shipper", NoParams, 1, 0));
        var bad = new Dictionary<string, JsonElement> { ["profile"] = JsonDocument.Parse("\"nope\"").RootElement.Clone() };
        Assert.Throws<ArgumentException>(() => StrategyRegistry.Create("rule-based", bad, 1, 0));
    }
}

public class PrototypeStrategyTests
{
    private static readonly IReadOnlyDictionary<string, JsonElement> NoParams = new Dictionary<string, JsonElement>();

    private static IStrategy Make(string name, ulong seed = 1) => StrategyRegistry.Create(name, NoParams, seed, 0);

    private static GameAction Choose(string name, GameState s) => Make(name).ChooseAction(s, Legal(s));

    /// <summary>Plays one game with the named strategy at seat <paramref name="seat"/> and random opponents; returns the end state.</summary>
    private static GameState Play(string name, int seat, ulong seed, out int harborRound)
    {
        var strategies = new IStrategy[3];
        for (int i = 0; i < 3; i++) strategies[i] = i == seat ? Make(name, seed) : new RandomStrategy(seed + (ulong)i + 1);
        var s = Setup.NewGame(seed);
        var legal = new List<GameAction>();
        harborRound = 0;
        while (!s.IsOver)
        {
            Rules.GetLegalActions(s, legal);
            var a = strategies[s.Actor].ChooseAction(s, legal);
            Assert.Contains(a, legal);
            Rules.Apply(s, a);
            if (harborRound == 0 && s.Owns(seat, BuildingId.Harbor)) harborRound = s.Round;
        }
        return s;
    }

    [Theory]
    [InlineData("corn-to-premium")]
    [InlineData("harbor-rush")]
    [InlineData("cheap-engine")]
    public void Only_Legal_Actions_And_Games_Finish(string name)
    {
        for (int game = 0; game < 60; game++) Play(name, game % 3, (ulong)game + 7, out _);
    }

    [Fact]
    public void Premium_Plays_Corn_First_Then_Goes_For_The_Producer_It_Already_Has()
    {
        var early = New();
        Array.Clear(early.FaceUp);
        early.FaceUp[(int)Good.Corn] = 1; early.FaceUp[(int)Good.Coffee] = 1;
        Start(early, 0, Role.Settler);
        Assert.Equal(A(ActionType.TakePlantation, (int)Good.Corn), Choose("corn-to-premium", early));

        var mid = New();
        mid.Round = 10; // past the 3-player switchRound (9)
        Own(mid, 0, BuildingId.TobaccoStorage, 1);
        Array.Clear(mid.FaceUp);
        mid.FaceUp[(int)Good.Corn] = 1; mid.FaceUp[(int)Good.Coffee] = 2; mid.FaceUp[(int)Good.Tobacco] = 1;
        Start(mid, 0, Role.Settler);
        Assert.Equal(A(ActionType.TakePlantation, (int)Good.Tobacco), Choose("corn-to-premium", mid)); // the one it can already process
    }

    [Fact]
    public void Premium_Chooses_Whichever_Of_Tobacco_And_Coffee_Is_Easier()
    {
        var s = New();
        s.Round = 10;
        Array.Clear(s.FaceUp);
        s.FaceUp[(int)Good.Coffee] = 1; s.FaceUp[(int)Good.Tobacco] = 1;
        SetTiles(s, 0, (int)Good.Coffee, 2); // coffee plantations already owned -> coffee is easier
        Start(s, 0, Role.Settler);
        Assert.Equal(A(ActionType.TakePlantation, (int)Good.Coffee), Choose("corn-to-premium", s));
    }

    [Fact]
    public void Premium_Buys_The_Producer_For_Its_Target_In_The_Middle_Game()
    {
        var s = New();
        s.Round = 10;
        SetTiles(s, 0, (int)Good.Tobacco, 2);
        s.Coins[0] = 6;
        Start(s, 0, Role.Builder);
        Assert.Equal(A(ActionType.Build, (int)BuildingId.TobaccoStorage), Choose("corn-to-premium", s));
    }

    [Fact]
    public void Harbor_Rush_Takes_Quarries_Buys_Only_The_Harbor_And_Builds_When_Affordable()
    {
        var s = New();
        Start(s, 0, Role.Settler);
        var quarries = new Dictionary<string, JsonElement> { ["quarryTarget"] = JsonDocument.Parse("3").RootElement.Clone() };
        Assert.Equal(ActionType.TakeQuarry, StrategyRegistry.Create("harbor-rush", quarries, 1, 0).ChooseAction(s, Legal(s)).Type); // quarries discount the Harbor
        var none = new Dictionary<string, JsonElement> { ["quarryTarget"] = JsonDocument.Parse("0").RootElement.Clone() };
        Assert.Equal(ActionType.TakePlantation, StrategyRegistry.Create("harbor-rush", none, 1, 0).ChooseAction(s, Legal(s)).Type); // quarryTarget 0: none
        Assert.Equal(ActionType.TakePlantation, Choose("harbor-rush", s).Type); // default: no quarries

        var poor = New();
        poor.Coins[0] = 6; // Harbor costs 8 - 1 (Builder) = 7
        Start(poor, 0, Role.Builder);
        Assert.Equal(GameAction.Pass, Choose("harbor-rush", poor)); // Hacienda etc. are affordable but not wanted yet

        var rich = New();
        rich.Coins[0] = 7;
        Start(rich, 0, Role.Builder);
        Assert.Equal(A(ActionType.Build, (int)BuildingId.Harbor), Choose("harbor-rush", rich));
    }

    [Fact]
    public void Harbor_Rush_Picks_Builder_When_It_Can_Pay_For_The_Harbor()
    {
        var s = New();
        s.Coins[0] = 7;
        Assert.Equal(A(ActionType.ChooseRole, (int)Role.Builder), Choose("harbor-rush", s));
    }

    [Fact]
    public void Harbor_Rush_Becomes_Captain_Once_It_Has_Harbor_And_Several_Goods()
    {
        var s = New();
        Own(s, 0, BuildingId.Harbor, 1);
        SetGoods(s, 0, (int)Good.Corn, 3);
        SetGoods(s, 0, (int)Good.Indigo, 2);
        SetGoods(s, 0, (int)Good.Sugar, 1);
        Assert.Equal(A(ActionType.ChooseRole, (int)Role.Captain), Choose("harbor-rush", s));

        var wants = New();
        Own(wants, 0, BuildingId.Harbor, 1);
        wants.Coins[0] = 9;
        Start(wants, 0, Role.Builder);
        Assert.Equal(A(ActionType.Build, (int)BuildingId.Wharf), Choose("harbor-rush", wants));
    }

    [Fact]
    public void Harbor_Rush_Mans_Quarries_And_Harbor_First()
    {
        var s = New();
        SetTiles(s, 0, GameConstants.QuarryType, 1);
        Own(s, 0, BuildingId.Harbor);
        s.ShipColonists = 1; // 2 colonists
        Start(s, 0, Role.Mayor);
        var first = Choose("harbor-rush", s);
        Assert.Equal(A(ActionType.PlaceColonist, GameConstants.QuarryType), first);
        Do(s, first);
        Assert.Equal(A(ActionType.PlaceColonist, 6 + (int)BuildingId.Harbor), Choose("harbor-rush", s));
    }

    [Fact]
    public void Harbor_Rush_Almost_Always_Gets_The_Harbor_And_Premium_Builds_A_Producer()
    {
        int harbor = 0, producer = 0, n = 90;
        for (int game = 0; game < n; game++)
        {
            Play("harbor-rush", game % 3, (ulong)game + 100, out int round);
            if (round > 0) harbor++;
            var s2 = Play("corn-to-premium", game % 3, (ulong)game + 100, out _);
            int seat = game % 3;
            if (s2.Owns(seat, BuildingId.TobaccoStorage) || s2.Owns(seat, BuildingId.CoffeeRoaster)) producer++;
        }
        Assert.True(harbor >= n * 0.9, $"Harbor in {harbor}/{n} games");
        Assert.True(producer >= n * 0.5, $"tobacco/coffee producer in {producer}/{n} games");
    }

    [Fact]
    public void Registry_Knows_All_Profiles()
    {
        foreach (var name in new[] { "corn-shipper", "corn-to-premium", "harbor-rush", "build-first" })
        {
            Assert.True(StrategyRegistry.IsKnown(name));
            var p = new Dictionary<string, JsonElement> { ["profile"] = JsonDocument.Parse($"\"{name}\"").RootElement.Clone() };
            Assert.NotNull(StrategyRegistry.Create("rule-based", p, 1, 0));
        }
    }
}

public class BuildFirstTests
{
    private static readonly IReadOnlyDictionary<string, JsonElement> NoParams = new Dictionary<string, JsonElement>();
    private static GameAction Choose(GameState s) => StrategyRegistry.Create("build-first", NoParams, 1, 0).ChooseAction(s, Legal(s));

    [Fact]
    public void Takes_Quarries_Then_Buys_Cheap_Useful_Buildings()
    {
        var s = New();
        Start(s, 0, Role.Settler);
        Assert.Equal(ActionType.TakeQuarry, Choose(s).Type);

        var b = New();
        b.Coins[0] = 5;
        Start(b, 0, Role.Builder);
        var buy = Choose(b);
        Assert.Equal(ActionType.Build, buy.Type); // low threshold: it spends coins
    }

    [Fact]
    public void Buys_Residence_When_The_Island_Is_Full_And_It_Can_Pay()
    {
        var s = New();
        Own(s, 0, BuildingId.SmallMarket, 1);
        SetTiles(s, 0, (int)Good.Corn, 4);
        SetTiles(s, 0, (int)Good.Indigo, 4);
        SetTiles(s, 0, (int)Good.Sugar, 4);
        s.Coins[0] = 9; // Residence costs 10 - 1 (Builder privilege)
        Start(s, 0, Role.Builder);
        Assert.Equal(A(ActionType.Build, (int)BuildingId.Residence), Choose(s));
    }

    [Fact]
    public void Mans_Production_Building_Before_Plain_Plantation()
    {
        var s = New();
        SetTiles(s, 0, (int)Good.Sugar, 1);
        Own(s, 0, BuildingId.SmallSugarMill);
        s.ShipColonists = 0; // only the privilege colonist
        Start(s, 0, Role.Mayor);
        // two circles are candidates with sugar tile + mill; with one colonist the mill (9) beats the lone tile (8 via mill)
        Assert.Equal(ActionType.PlaceColonist, Choose(s).Type);
    }

    [Fact]
    public void Beats_Random_Players_And_Buys_Many_Buildings()
    {
        var cfg = new SimulationConfig { Games = 300, Seed = 6 };
        cfg.Seats[0].Strategy = "build-first";
        var r = BatchSimulator.Run(cfg, new BatchOptions(), CancellationToken.None);
        Assert.True(r.Summary[0].WinShare > 0.8, $"win share {r.Summary[0].WinShare}");
        Assert.True(r.Games.Average(g => g.Players.First(p => p.SeatId == "A").BuildingPoints) > 8);
    }

    [Fact]
    public void Plays_Only_Legal_Actions_In_3_And_4_Player_Games()
    {
        foreach (int players in new[] { 3, 4 })
            for (int game = 0; game < 30; game++)
            {
                var strategies = Enumerable.Range(0, players)
                    .Select(i => i == 0 ? StrategyRegistry.Create("build-first", NoParams, 1, 0) : new RandomStrategy((ulong)(game * 7 + i))).ToArray();
                var s = Setup.NewGame((ulong)game + 3, players: players);
                var legal = new List<GameAction>();
                while (!s.IsOver)
                {
                    Rules.GetLegalActions(s, legal);
                    var a = strategies[s.Actor].ChooseAction(s, legal);
                    Assert.Contains(a, legal);
                    Rules.Apply(s, a);
                }
            }
    }
}

public class ProspectorValueTests
{
    private static readonly IReadOnlyDictionary<string, JsonElement> NoParams = new Dictionary<string, JsonElement>();

    [Theory]
    [InlineData("corn-shipper")]
    [InlineData("corn-to-premium")]
    [InlineData("harbor-rush")]
    [InlineData("build-first")]
    public void Prospector_Is_Worth_Its_Coins_Not_A_Trader_Sale(string name)
    {
        var strategy = StrategyRegistry.Create(name, NoParams, 1, 0);
        var options = new List<GameAction>
        {
            new(ActionType.ChooseRole, (int)Role.Trader),
            new(ActionType.ChooseRole, (int)Role.Prospector),
        };

        var rich = Setup.NewGame(1, players: 4);
        rich.Goods[0 * 5 + (int)Good.Coffee] = 2; rich.Goods[0 * 5 + (int)Good.Tobacco] = 2;
        Assert.Equal(Role.Trader, (Role)strategy.ChooseAction(rich, options).A); // goods to sell beat one coin

        var poor = Setup.NewGame(1, players: 4);
        poor.RoleCoins[(int)Role.Prospector] = 3; // nothing to sell, coins on the card
        Assert.Equal(Role.Prospector, (Role)strategy.ChooseAction(poor, options).A);
    }
}
