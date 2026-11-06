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
