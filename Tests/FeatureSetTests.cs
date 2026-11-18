using System.Text.Json;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies.Mcts;
using Xunit;

namespace PuertoRico.Tests;

/// <summary>Feature sets live side by side: version 1 is frozen, version 2 = version 1 + derived features.</summary>
public class FeatureSetTests
{
    private static GameState RandomState(ulong seed, int players, int steps)
    {
        var s = Setup.NewGame(seed, players: players);
        var rng = new Random((int)seed);
        for (int i = 0; i < steps && !s.IsOver; i++)
        {
            var legal = Sc.Legal(s);
            Sc.Do(s, legal[rng.Next(legal.Count)]);
        }
        return s;
    }

    private static int Index(FeatureSet set, string name) => set.Names.ToList().IndexOf(name);

    [Fact]
    public void Registry_finds_sets_by_version_and_by_names_and_refuses_the_rest()
    {
        Assert.Equal(new[] { 1, 2 }, FeatureSets.All.Select(f => f.Version).ToArray());
        Assert.Same(FeatureSets.V2, FeatureSets.Latest);
        Assert.Equal(FeatureSets.LatestVersion, FeatureSets.Latest.Version);
        Assert.Same(FeatureSets.V1, FeatureSets.Find(FeatureSets.V1.Names));
        Assert.Same(FeatureSets.V2, FeatureSets.Find(FeatureSets.V2.Names));
        Assert.Null(FeatureSets.Find(FeatureSets.V1.Names.Take(10).ToList()));
        var e = Assert.Throws<ArgumentException>(() => FeatureSets.Get(3));
        Assert.Contains("supported: 1, 2", e.Message);
        Assert.Equal(430, FeatureSets.V1.Count);
    }

    [Fact]
    public void Version_2_is_version_1_unchanged_plus_new_unique_features()
    {
        var v1 = FeatureSets.V1.Names;
        var v2 = FeatureSets.V2.Names;
        Assert.Equal(v1, v2.Take(v1.Count).ToList());
        Assert.Equal(v2.Count, v2.Distinct().Count());
        // 2 global + roles x 4 seats + 4 blocks x 13 per-seat features
        Assert.Equal(v1.Count + 2 + GameConstants.MaxRoleCount * 4 + 4 * 13, v2.Count);
    }

    [Theory]
    [InlineData(3)]
    [InlineData(4)]
    public void Version_2_rows_start_with_the_version_1_row_and_stay_small_integers(int players)
    {
        for (ulong seed = 1; seed <= 6; seed++)
        {
            var s = RandomState(seed, players, 40 + (int)seed * 25);
            for (int me = 0; me < players; me++)
            {
                var a = FeatureSets.V1.Extract(s, me);
                var b = FeatureSets.V2.Extract(s, me);
                Assert.Equal(a, b.Take(a.Length).ToArray());
                Assert.All(b, v => Assert.True(v >= short.MinValue && v <= short.MaxValue && v == Math.Floor(v)));
            }
        }
    }

    [Fact]
    public void Extraction_is_repeatable_when_the_row_buffers_are_reused()
    {
        var set = FeatureSets.V2;
        var rows = new float[GameConstants.MaxPlayers][];
        for (int i = 0; i < rows.Length; i++) rows[i] = new float[set.Count];
        var scratch = new float[set.ScratchLength];
        var s1 = RandomState(3, 4, 120);
        var s2 = RandomState(4, 4, 60);
        set.ExtractAll(s1, rows, scratch);
        var first = rows[1].ToArray();
        set.ExtractAll(s2, rows, scratch); // other state in the same buffers
        set.ExtractAll(s1, rows, scratch);
        Assert.Equal(first, rows[1]);
    }

    [Fact]
    public void Seat_blocks_are_relative_to_me_and_the_fourth_block_is_empty_with_three_players()
    {
        var s = Sc.New(5); // 3 players
        Sc.SetGoods(s, 0, (int)Good.Corn, 2);
        Sc.SetGoods(s, 2, (int)Good.Coffee, 1);
        var f = FeatureSets.V2.Extract(s, 2);
        Assert.Equal(1, f[Index(FeatureSets.V2, "p0_goodsTotal")]);  // me = seat 2
        Assert.Equal(2, f[Index(FeatureSets.V2, "p1_goodsTotal")]);  // next seat = seat 0
        Assert.Equal(0, f[Index(FeatureSets.V2, "p3_goodsTotal")]);
        Assert.Equal(0, f[Index(FeatureSets.V2, "p3_citySpacesLeft")]);
        Assert.Equal(12, f[Index(FeatureSets.V2, "p0_citySpacesLeft")]);
    }

    [Fact]
    public void Shippable_follows_the_ship_rules_with_a_greedy_assignment()
    {
        var s = Sc.New(7);
        s.ShipCap[0] = 4; s.ShipCap[1] = 5; s.ShipCap[2] = 6;
        Array.Clear(s.ShipLoad);
        Sc.SetGoods(s, 0, (int)Good.Indigo, 3);
        Sc.SetGoods(s, 0, (int)Good.Sugar, 2);
        int shippable = Index(FeatureSets.V2, "p0_shippable");
        // empty ships: the biggest good gets the biggest ship: min(3, 6) + min(2, 5)
        Assert.Equal(5, FeatureSets.V2.Extract(s, 0)[shippable]);
        // indigo already sits on the 4-barrel ship with 1 barrel: only 3 more fit there; sugar then takes the biggest empty ship
        s.ShipLoad[0] = 1; s.ShipGood[0] = (int)Good.Indigo;
        Assert.Equal(3 + 2, FeatureSets.V2.Extract(s, 0)[shippable]);
        // sugar is already on a full ship: it cannot go anywhere (a good loaded elsewhere may only go to its own ship)
        s.ShipLoad[1] = 5; s.ShipGood[1] = (int)Good.Sugar;
        Assert.Equal(3, FeatureSets.V2.Extract(s, 0)[shippable]);
    }

    [Fact]
    public void Trader_features_count_goods_that_can_be_sold_and_their_best_price()
    {
        var s = Sc.New(8);
        Sc.SetGoods(s, 1, (int)Good.Coffee, 1);
        Sc.SetGoods(s, 1, (int)Good.Corn, 2);
        s.Phase = Phase.ChooseRole;
        int tradable = Index(FeatureSets.V2, "p0_tradableGoods"), best = Index(FeatureSets.V2, "p0_bestSalePrice");
        var f = FeatureSets.V2.Extract(s, 1);
        Assert.Equal(2, f[tradable]);
        Assert.Equal(GameConstants.BasePrice[(int)Good.Coffee], f[best]);
        // coffee already in the trade house (and no Office): only corn is left to sell
        s.TradeHouse[0] = (int)Good.Coffee; s.TradeCount = 1;
        f = FeatureSets.V2.Extract(s, 1);
        Assert.Equal(1, f[tradable]);
        Assert.Equal(GameConstants.BasePrice[(int)Good.Corn], f[best]);
        // a full trade house sells nothing
        s.TradeCount = GameConstants.TradeSlots;
        Assert.Equal(0, FeatureSets.V2.Extract(s, 1)[tradable]);
    }

    [Fact]
    public void Builder_features_count_the_buildings_a_seat_could_buy_now()
    {
        var s = Sc.New(9);
        s.Coins[0] = 1;
        int affordable = Index(FeatureSets.V2, "p0_affordableBuildings"), bestVp = Index(FeatureSets.V2, "p0_bestAffordableVp");
        int cost1 = Buildings.All.Count(b => b.Cost == 1);
        var f = FeatureSets.V2.Extract(s, 0);
        Assert.Equal(cost1, f[affordable]);
        Assert.Equal(1, f[bestVp]);
        s.Coins[0] = 0;
        Assert.Equal(0, FeatureSets.V2.Extract(s, 0)[affordable]);
        s.Coins[0] = 99;
        var rich = FeatureSets.V2.Extract(s, 0);
        Assert.True(rich[affordable] > cost1);
        Assert.True(rich[bestVp] >= 3);
    }

    [Fact]
    public void Building_counts_and_unmanned_large_buildings()
    {
        var s = Sc.New(10);
        Sc.Own(s, 0, BuildingId.SmallMarket, occupied: 1);
        Sc.Own(s, 0, BuildingId.Hacienda);
        Sc.Own(s, 0, BuildingId.GuildHall);          // large, no colonist
        Sc.Own(s, 0, BuildingId.CityHall, occupied: 1);
        var f = FeatureSets.V2.Extract(s, 0);
        Assert.Equal(2, f[Index(FeatureSets.V2, "p0_smallBuildings")]);
        Assert.Equal(2, f[Index(FeatureSets.V2, "p0_largeBuildings")]);
        Assert.Equal(1, f[Index(FeatureSets.V2, "p0_unfilledLarge")]);
        Assert.Equal(12 - s.CitySpacesUsed(0), f[Index(FeatureSets.V2, "p0_citySpacesLeft")]);
        Assert.Equal(12 - s.CitySpacesUsed(0), f[Index(FeatureSets.V2, "minCitySpacesLeft")]);
    }

    [Fact]
    public void Role_ownership_and_picks_left_follow_the_round()
    {
        var s = Sc.New(11);
        Sc.Start(s, owner: 1, Role.Settler);           // seat 1 took the Settler: 1 of 3 picks done
        var f = FeatureSets.V2.Extract(s, 1);
        Assert.Equal(1, f[Index(FeatureSets.V2, "roleTakenRel0_Settler")]);
        Assert.Equal(2, f[Index(FeatureSets.V2, "picksLeft")]);
        f = FeatureSets.V2.Extract(s, 2);              // seen from seat 2, seat 1 is two seats ahead
        Assert.Equal(1, f[Index(FeatureSets.V2, "roleTakenRel2_Settler")]);
        Assert.Equal(0, f[Index(FeatureSets.V2, "roleTakenRel0_Settler")]);
    }

    private static string WriteMlp(FeatureSet set, string dir)
    {
        int f = set.Count;
        var w1 = new float[1][];
        w1[0] = new float[f];
        w1[0][Index(set, "round")] = 0.1f;
        var json = JsonSerializer.Serialize(new
        {
            format = "mlp",
            features = set.Names,
            mean = new float[f],
            scale = Enumerable.Repeat(1f, f).ToArray(),
            activation = "relu",
            output = "sigmoid",
            layers = new object[] { new { weights = w1, bias = new[] { 0.1f } }, new { weights = new[] { new[] { 1f } }, bias = new[] { 0f } } },
        });
        string path = Path.Combine(dir, $"mlp-v{set.Version}.json");
        File.WriteAllText(path, json);
        return path;
    }

    [Fact]
    public void A_model_of_either_version_loads_with_its_own_feature_set_and_plays_mcts()
    {
        string dir = Path.Combine(Path.GetTempPath(), "pr-featuresets-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            foreach (var set in FeatureSets.All)
            {
                string path = WriteMlp(set, dir);
                var model = ValueModels.Load(path);
                Assert.Same(set, model.Features);
                var cfg = new SimulationConfig { Name = "m", Players = 4, Games = 1, Seed = 2, Seats = new List<SeatConfig>() };
                var m = new SeatConfig { Id = "m", Strategy = "mcts" };
                m.Params["simulations"] = JsonSerializer.SerializeToElement(10);
                m.Params["valueModel"] = JsonSerializer.SerializeToElement(path);
                cfg.Seats.Add(m);
                for (int i = 1; i < 4; i++) cfg.Seats.Add(new SeatConfig { Id = $"c{i}", Strategy = "cheap-engine" });
                var a = GameRunner.Play(cfg, 0);
                Assert.Equal(System.Text.Json.JsonSerializer.Serialize(a), System.Text.Json.JsonSerializer.Serialize(GameRunner.Play(cfg, 0)));
                Assert.NotEmpty(a.Winners);
            }
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public void A_model_with_an_unknown_feature_list_names_the_difference_and_the_supported_versions()
    {
        string dir = Path.Combine(Path.GetTempPath(), "pr-featuresets-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            string path = WriteMlp(FeatureSets.V2, dir);
            string text = File.ReadAllText(path).Replace("\"picksLeft\"", "\"picksLeftX\"");
            File.WriteAllText(path, text);
            var e = Assert.Throws<InvalidDataException>(() => MlpValueModel.Parse(File.ReadAllText(path)));
            Assert.Contains("picksLeftX", e.Message);
            Assert.Contains("feature version 2 expects 'picksLeft'", e.Message);
            Assert.Contains("(1, 2)", e.Message);
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public void Dump_uses_the_newest_feature_set_unless_a_version_is_asked_for()
    {
        string dir = Path.Combine(Path.GetTempPath(), "pr-featuredump-" + Guid.NewGuid().ToString("N"));
        try
        {
            var cfg = new SimulationConfig { Name = "d", Players = 3, Games = 8, Seed = 4 };
            foreach (var (features, expected) in new (FeatureSet?, FeatureSet)[] { (null, FeatureSets.Latest), (FeatureSets.V1, FeatureSets.V1), (FeatureSets.V2, FeatureSets.V2) })
            {
                string path = Path.Combine(dir, $"d{expected.Version}.bin");
                var r = PositionDump.Run(cfg, path, 0.2, features: features);
                Assert.True(r.Rows > 0);
                Assert.Equal(r.Rows * PositionDump.RecordBytes(expected), new FileInfo(path).Length);
                using var meta = JsonDocument.Parse(File.ReadAllText(path + ".json"));
                Assert.Equal(expected.Version, meta.RootElement.GetProperty("featureVersion").GetInt32());
                Assert.Equal(expected.Count, meta.RootElement.GetProperty("featureCount").GetInt32());
                Assert.Equal(expected.Names.ToArray(), meta.RootElement.GetProperty("featureNames").EnumerateArray().Select(e => e.GetString()!).ToArray());
            }
            // the same games, sampled the same way: version 1 is the front part of every version 2 record
            var v1 = File.ReadAllBytes(Path.Combine(dir, "d1.bin"));
            var v2 = File.ReadAllBytes(Path.Combine(dir, "d2.bin"));
            int n1 = PositionDump.RecordBytes(FeatureSets.V1), n2 = PositionDump.RecordBytes(FeatureSets.V2);
            Assert.Equal(v1.Length / n1, v2.Length / n2);
            Assert.Equal(v1.AsSpan(0, n1).ToArray(), v2.AsSpan(0, n1).ToArray());
        }
        finally { if (Directory.Exists(dir)) Directory.Delete(dir, true); }
    }
}
