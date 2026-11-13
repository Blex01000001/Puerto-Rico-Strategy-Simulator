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

public class WharfAndMonopolyTests
{
    private static readonly IReadOnlyDictionary<string, JsonElement> NoParams = new Dictionary<string, JsonElement>();

    private static void PlayGamesAgainstRandom(Func<IStrategy> make)
    {
        for (int game = 0; game < 100; game++)
        {
            var mine = make();
            var rnd1 = new RandomStrategy((ulong)game);
            var rnd2 = new RandomStrategy((ulong)game + 1);
            var s = Setup.NewGame((ulong)game + 11);
            var legal = new List<GameAction>();
            int steps = 0;
            while (!s.IsOver)
            {
                Rules.GetLegalActions(s, legal);
                IStrategy who = s.Actor == game % 3 ? mine : (s.Actor == (game + 1) % 3 ? rnd1 : rnd2);
                var a = who.ChooseAction(s, legal);
                Assert.Contains(a, legal);
                Rules.Apply(s, a);
                Assert.True(++steps < 20000);
            }
            Assert.Null(Invariants.Check(s));
        }
    }

    [Fact] public void Wharf_Rush_Plays_Legal_Games() => PlayGamesAgainstRandom(() => new WharfRushStrategy(NoParams));
    [Fact] public void Corn_Monopoly_Plays_Legal_Games() => PlayGamesAgainstRandom(() => new CornMonopolyStrategy(NoParams));
    [Fact] public void Corn_Monopoly_Tiles_Plays_Legal_Games() => PlayGamesAgainstRandom(() => new CornMonopolyStrategy(NoParams, grab: true, hoard: false));
    [Fact] public void Corn_Monopoly_Hoard_Plays_Legal_Games() => PlayGamesAgainstRandom(() => new CornMonopolyStrategy(NoParams, grab: false, hoard: true));
    [Fact] public void Wharf_Premium_Plays_Legal_Games() => PlayGamesAgainstRandom(() => new WharfPremiumStrategy(NoParams));

    [Fact]
    public void Monopoly_Variants_Split_The_Two_Means()
    {
        // tiles-only: ships corn like the corn shipper; hoard-only: ships the other good first and keeps the corn
        GameState Captain()
        {
            var s = New();
            SetGoods(s, 0, (int)Good.Corn, 3);
            SetGoods(s, 0, (int)Good.Indigo, 1);
            return Start(s, 0, Role.Captain);
        }
        var s1 = Captain();
        Assert.Equal((int)Good.Corn, new CornMonopolyStrategy(NoParams, grab: true, hoard: false).ChooseAction(s1, Legal(s1)).A);
        var s2 = Captain();
        Assert.Equal((int)Good.Indigo, new CornMonopolyStrategy(NoParams, grab: false, hoard: true).ChooseAction(s2, Legal(s2)).A);
    }

    [Fact]
    public void Wharf_Premium_Buys_The_Producer_First_Then_Only_The_Wharf_And_Sells_The_Premium_Good()
    {
        var s = New();
        SetTiles(s, 0, (int)Good.Coffee, 1, occupied: 1);
        s.Coins[0] = 9;
        Start(s, 0, Role.Builder);
        Assert.Equal(new GameAction(ActionType.Build, (int)BuildingId.CoffeeRoaster), new WharfPremiumStrategy(NoParams).ChooseAction(s, Legal(s)));

        var s2 = New();
        SetTiles(s2, 0, (int)Good.Coffee, 1, occupied: 1);
        Own(s2, 0, BuildingId.CoffeeRoaster, occupied: 1);
        s2.Coins[0] = 9;
        Start(s2, 0, Role.Builder);
        Assert.Equal(new GameAction(ActionType.Build, (int)BuildingId.Wharf), new WharfPremiumStrategy(NoParams).ChooseAction(s2, Legal(s2)));

        var s3 = New();
        Own(s3, 0, BuildingId.CoffeeRoaster, occupied: 1);
        SetGoods(s3, 0, (int)Good.Coffee, 1);
        SetGoods(s3, 0, (int)Good.Corn, 1);
        Start(s3, 0, Role.Trader);
        Assert.Equal(new GameAction(ActionType.Sell, (int)Good.Coffee), new WharfPremiumStrategy(NoParams).ChooseAction(s3, Legal(s3)));
    }

    [Fact]
    public void Wharf_Rush_Ships_The_Biggest_Stack_On_The_Wharf_First()
    {
        // rules.md section 4 (Wharf): the private ship takes all barrels of one good, ignoring capacity
        var s = New();
        Own(s, 0, BuildingId.Wharf, occupied: 1);
        SetGoods(s, 0, (int)Good.Corn, 6);
        SetGoods(s, 0, (int)Good.Indigo, 2);
        s.GoodsSupply[(int)Good.Corn] -= 6;
        s.GoodsSupply[(int)Good.Indigo] -= 2;
        Start(s, 0, Role.Captain);
        var a = new WharfRushStrategy(NoParams).ChooseAction(s, Legal(s));
        Assert.Equal(new GameAction(ActionType.LoadWharf, (int)Good.Corn), a);
    }

    [Fact]
    public void Wharf_Rush_Buys_The_Wharf_Once_The_Farming_Phase_Is_Over()
    {
        var s = New();
        s.Round = 8; // past wharfReadyRound
        s.Coins[0] = 9;
        Start(s, 0, Role.Builder);
        var a = new WharfRushStrategy(NoParams).ChooseAction(s, Legal(s));
        Assert.Equal(new GameAction(ActionType.Build, (int)BuildingId.Wharf), a);
    }

    [Fact]
    public void Corn_Monopoly_Takes_Corn_Plantations_And_Never_Picks_Captain_When_It_Can_Avoid_It()
    {
        var s = New();
        s.FaceUp[(int)Good.Corn] = 1;
        Start(s, 0, Role.Settler);
        var a = new CornMonopolyStrategy(NoParams).ChooseAction(s, Legal(s));
        Assert.Equal(new GameAction(ActionType.TakePlantation, (int)Good.Corn), a);

        var s2 = New();
        SetGoods(s2, 0, (int)Good.Corn, 3);
        s2.Governor = 0; s2.Actor = 0; s2.Phase = Phase.ChooseRole;
        var role = new CornMonopolyStrategy(NoParams).ChooseAction(s2, Legal(s2));
        Assert.NotEqual(new GameAction(ActionType.ChooseRole, (int)Role.Captain), role);
    }

    [Fact]
    public void Corn_Monopoly_Never_Sells_Corn_And_Ships_Other_Goods_First()
    {
        var s = New();
        SetGoods(s, 0, (int)Good.Corn, 3);
        SetGoods(s, 0, (int)Good.Indigo, 1);
        Start(s, 0, Role.Captain);
        var a = new CornMonopolyStrategy(NoParams).ChooseAction(s, Legal(s));
        Assert.Equal(ActionType.LoadShip, a.Type);
        Assert.Equal((int)Good.Indigo, a.A);
    }
}

public class ActionScoreTests
{
    private static readonly IReadOnlyDictionary<string, JsonElement> NoParams = new Dictionary<string, JsonElement>();

    private sealed class ScoreSink : PuertoRico.Engine.Events.IGameEventSink
    {
        public int Decisions, Scored, Violations;
        private IReadOnlyList<ScoredAction>? _scores;
        public bool Enabled => true;
        public void OnScores(IReadOnlyList<ScoredAction> scores) => _scores = scores;
        public void OnDecision(GameState before, GameAction action)
        {
            Decisions++;
            if (_scores != null)
            {
                Scored++;
                // outside the Mayor phase the chosen action is the first one with the highest score
                if (before.Phase != Phase.Mayor && _scores.First(x => x.Score == _scores.Max(y => y.Score)).Action != action) Violations++;
                if (_scores.All(x => x.Action != action)) Violations++;
            }
            _scores = null;
        }
    }

    [Fact]
    public void Heuristic_Reports_Scores_Only_When_Asked_And_The_Choice_Never_Changes()
    {
        var s = Sc.Start(Sc.New(), 0, Role.Builder);
        Sc.Own(s, 0, BuildingId.Hacienda);
        s.Coins[0] = 9;
        var legal = Sc.Legal(s);
        var quiet = new HarborRushStrategy(NoParams);
        var loud = new HarborRushStrategy(NoParams) { RecordScores = true };
        var a = quiet.ChooseAction(s, legal);
        var b = loud.ChooseAction(s, legal);
        Assert.Equal(a, b);                      // recording scores never changes the decision
        Assert.Null(quiet.LastScores);
        Assert.Equal(legal.Count, loud.LastScores!.Count);
        Assert.Equal(legal, loud.LastScores.Select(x => x.Action));
        Assert.Equal(loud.LastScores.Max(x => x.Score), loud.LastScores.First(x => x.Action == b).Score);
    }

    [Fact]
    public void Replay_Sink_Gets_The_Scores_Of_Hand_Written_Strategies_And_Mass_Runs_Record_None()
    {
        var cfg = new SimulationConfig { Name = "scores", Players = 3, Games = 2, Seed = 4, Seats = new List<SeatConfig>
        {
            new() { Id = "h", Strategy = "harbor-rush" }, new() { Id = "c", Strategy = "corn-shipper" }, new() { Id = "r", Strategy = "random" },
        } };
        var sink = new ScoreSink();
        GameRunner.Play(cfg, 0, sink, out _);
        Assert.True(sink.Scored > 20);
        Assert.True(sink.Scored < sink.Decisions);   // random seat, forced moves: no scores
        Assert.Equal(0, sink.Violations);
        // a normal run without a sink never switches recording on
        var strategy = new CornShipperStrategy(NoParams);
        Assert.False(strategy.RecordScores);
    }
}

public class RandomTieTests
{
    private static IReadOnlyDictionary<string, JsonElement> Params(double randomTies) =>
        new Dictionary<string, JsonElement> { ["randomTies"] = JsonSerializer.SerializeToElement(randomTies) };

    [Fact]
    public void Default_Breaks_Ties_By_Engine_Order_And_Random_Ties_Spread_The_Choice_Over_The_Tied_Plantations()
    {
        // the corn monopolist values every non-corn plantation at 1: with no corn and no quarry on offer they all tie for the top score
        GameState Settler()
        {
            var s = Sc.New();
            Array.Clear(s.FaceUp);
            for (int g = (int)Good.Indigo; g <= (int)Good.Coffee; g++) s.FaceUp[g] = 1;
            s.QuarrySupply = 0;
            return Sc.Start(s, 0, Role.Settler);
        }
        var state = Settler();
        var legal = Sc.Legal(state);
        Assert.Equal(4, legal.Count(a => a.Type == ActionType.TakePlantation));

        var first = new CornMonopolyStrategy(NoParamsOf()).ChooseAction(state, legal);
        Assert.Equal(new GameAction(ActionType.TakePlantation, (int)Good.Indigo), first); // engine order: the lowest good
        for (ulong seed = 1; seed <= 20; seed++)
            Assert.Equal(first, new CornMonopolyStrategy(NoParamsOf()) { Seed = seed }.ChooseAction(state, legal)); // the default ignores the seed

        var counts = new Dictionary<GameAction, int>();
        for (ulong seed = 1; seed <= 400; seed++)
        {
            var a = new CornMonopolyStrategy(Params(1)) { Seed = seed }.ChooseAction(state, legal);
            Assert.Contains(a, legal);
            counts[a] = counts.GetValueOrDefault(a) + 1;
        }
        Assert.Equal(4, counts.Count);                    // every tied plantation gets chosen sometimes
        Assert.All(counts.Values, n => Assert.InRange(n, 60, 140)); // roughly a quarter each (400 draws)
        Assert.Equal(new CornMonopolyStrategy(Params(1)) { Seed = 5 }.ChooseAction(state, legal),
                     new CornMonopolyStrategy(Params(1)) { Seed = 5 }.ChooseAction(state, legal)); // same seed, same choice
    }

    private static IReadOnlyDictionary<string, JsonElement> NoParamsOf() => new Dictionary<string, JsonElement>();

    [Fact]
    public void Random_Ties_Keep_Games_Legal_And_Reproducible()
    {
        var cfg = new SimulationConfig { Name = "rt", Players = 3, Games = 3, Seed = 9, Seats = new List<SeatConfig>
        {
            new() { Id = "a", Strategy = "corn-monopoly", Params = new Dictionary<string, JsonElement> { ["randomTies"] = JsonSerializer.SerializeToElement(1.0) } },
            new() { Id = "b", Strategy = "harbor-rush", Params = new Dictionary<string, JsonElement> { ["randomTies"] = JsonSerializer.SerializeToElement(2.0) } },
            new() { Id = "c", Strategy = "build-first" },
        } };
        var r1 = GameRunner.Play(cfg, 1, null, out var f1);
        var r2 = GameRunner.Play(cfg, 1, null, out var f2);
        Assert.Equal(r1.Decisions, r2.Decisions);
        Assert.Equal(r1.Winners, r2.Winners);
        Assert.Null(Invariants.Check(f1));
        Assert.True(f1.IsOver && f2.IsOver);
    }
}

public class TieBreakRuleTests
{
    private static IReadOnlyDictionary<string, JsonElement> P(params (string Key, object Value)[] items) =>
        items.ToDictionary(x => x.Key, x => JsonSerializer.SerializeToElement(x.Value));

    /// <summary>Settler phase where indigo, sugar, tobacco and coffee are face up (no corn, no quarry): the corn monopolist values them all at 1.</summary>
    private static GameState Settler(bool cornFaceUp = false)
    {
        var s = Sc.New();
        Array.Clear(s.FaceUp);
        for (int g = (int)Good.Indigo; g <= (int)Good.Coffee; g++) s.FaceUp[g] = 1;
        if (cornFaceUp) s.FaceUp[(int)Good.Corn] = 1;
        s.QuarrySupply = 0;
        return Sc.Start(s, 0, Role.Settler);
    }

    private static GameAction Take(Good g) => new(ActionType.TakePlantation, (int)g);

    [Fact]
    public void Fixed_Order_Decides_Between_Equal_Scores_And_Default_Is_Unchanged()
    {
        var s = Settler();
        var legal = Sc.Legal(s);
        Assert.Equal(Take(Good.Indigo), new CornMonopolyStrategy(P()).ChooseAction(s, legal));                                 // default: engine order
        Assert.Equal(Take(Good.Sugar), new CornMonopolyStrategy(P(("tieTile", "sugar>indigo"))).ChooseAction(s, legal));
        Assert.Equal(Take(Good.Coffee), new CornMonopolyStrategy(P(("tieTile", "coffee,tobacco"))).ChooseAction(s, legal));    // commas work too
        Assert.Equal(Take(Good.Coffee), new CornMonopolyStrategy(P(("tieTile", "coffee"))).ChooseAction(s, legal));            // unlisted tokens rank last
        Assert.Equal(Take(Good.Indigo), new CornMonopolyStrategy(P(("tieGood", "coffee"))).ChooseAction(s, legal));            // another category: no effect here
    }

    [Fact]
    public void The_Second_Criterion_Never_Overrides_A_Real_Score_Difference()
    {
        var s = Settler(cornFaceUp: true);   // corn is worth 20 to the monopolist, the others 1
        var legal = Sc.Legal(s);
        Assert.Equal(Take(Good.Corn), new CornMonopolyStrategy(P(("tieTile", "coffee>sugar"))).ChooseAction(s, legal));
    }

    [Fact]
    public void Unknown_Tokens_Are_Rejected_With_The_List_Of_Known_Ones()
    {
        var s = Settler();
        var e = Assert.Throws<ArgumentException>(() => new CornMonopolyStrategy(P(("tieTile", "suagr>indigo"))).ChooseAction(s, Sc.Legal(s)));
        Assert.Contains("suagr", e.Message);
        Assert.Contains("hacienda", e.Message);
    }

    private static GameState Craftsman()
    {
        var s = Sc.New();
        SetTiles(s, 0, (int)Good.Corn, 1, occupied: 1);
        SetTiles(s, 0, (int)Good.Indigo, 1, occupied: 1);
        SetTiles(s, 0, (int)Good.Sugar, 1, occupied: 1);
        Own(s, 0, BuildingId.SmallIndigoPlant, occupied: 1);
        Own(s, 0, BuildingId.SmallSugarMill, occupied: 1);
        // the opponent in seat 1 produces 2 indigo and 1 sugar
        SetTiles(s, 1, (int)Good.Indigo, 2, occupied: 2);
        SetTiles(s, 1, (int)Good.Sugar, 1, occupied: 1);
        Own(s, 1, BuildingId.LargeIndigoPlant, occupied: 2);
        Own(s, 1, BuildingId.LargeSugarMill, occupied: 1);
        return Sc.Start(s, 0, Role.Craftsman);
    }

    private static GameAction Bonus(Good g) => new(ActionType.CraftsmanBonus, (int)g);

    [Fact]
    public void Bonus_Good_Order_And_The_Reserved_Opponent_Dependence_Feature()
    {
        var s = Craftsman();
        var legal = Sc.Legal(s);
        Assert.Equal(3, legal.Count(a => a.Type == ActionType.CraftsmanBonus));
        // the harbor rush scores corn, indigo and sugar equally for the bonus: engine order picks corn
        Assert.Equal(Bonus(Good.Corn), new HarborRushStrategy(P()).ChooseAction(s, legal));
        Assert.Equal(Bonus(Good.Sugar), new HarborRushStrategy(P(("tieGood", "sugar>indigo"))).ChooseAction(s, legal));

        // opponent dependence = barrels the opponents produce: indigo 2, sugar 1, corn 0 (public information only)
        Assert.Equal(2, TieBreakRules.OpponentDependence(s, 0, (int)Good.Indigo));
        Assert.Equal(1, TieBreakRules.OpponentDependence(s, 0, (int)Good.Sugar));
        Assert.Equal(0, TieBreakRules.OpponentDependence(s, 0, (int)Good.Corn));
        Assert.Equal(Bonus(Good.Indigo), new HarborRushStrategy(P(("tieOpponent", 1))).ChooseAction(s, legal));   // blocking: the good they need most
        Assert.Equal(Bonus(Good.Corn), new HarborRushStrategy(P(("tieOpponent", -1))).ChooseAction(s, legal));    // avoiding it
        // the fixed order is the first key, the opponent feature only the second
        Assert.Equal(Bonus(Good.Sugar), new HarborRushStrategy(P(("tieGood", "sugar"), ("tieOpponent", 1))).ChooseAction(s, legal));
    }

    [Fact]
    public void Tie_Rules_Keep_Games_Legal_And_Reproducible_And_Are_Reported_To_The_Replay()
    {
        var parameters = new Dictionary<string, JsonElement>
        {
            ["tieTile"] = JsonSerializer.SerializeToElement("sugar>indigo>coffee"), ["tieGood"] = JsonSerializer.SerializeToElement("coffee>sugar"),
            ["tieRole"] = JsonSerializer.SerializeToElement("builder>settler"), ["tieBuild"] = JsonSerializer.SerializeToElement("pass"),
            ["tieOpponent"] = JsonSerializer.SerializeToElement(0.5),
        };
        var cfg = new SimulationConfig { Name = "tie", Players = 3, Games = 3, Seed = 11, Seats = new List<SeatConfig>
        {
            new() { Id = "a", Strategy = "build-first", Params = parameters }, new() { Id = "b", Strategy = "harbor-rush", Params = parameters }, new() { Id = "c", Strategy = "corn-shipper" },
        } };
        var r1 = GameRunner.Play(cfg, 2, null, out var f1);
        var r2 = GameRunner.Play(cfg, 2, null, out _);
        Assert.Equal(r1.Winners, r2.Winners);
        Assert.Null(Invariants.Check(f1));

        var sink = new CollectScores();
        GameRunner.Play(cfg, 2, sink, out _);
        Assert.Contains(sink.All, x => x.TieRank >= 0);   // the rank in the tie order reaches the replay
    }

    private sealed class CollectScores : PuertoRico.Engine.Events.IGameEventSink
    {
        public List<ScoredAction> All { get; } = new();
        public bool Enabled => true;
        public void OnScores(IReadOnlyList<ScoredAction> scores) => All.AddRange(scores);
        public void OnDecision(GameState before, GameAction action) { }
    }
}
