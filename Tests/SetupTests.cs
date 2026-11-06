using PuertoRico.Engine.Game;
using Xunit;

namespace PuertoRico.Tests;

// rules.md section 1 (setup) and section 3 (building table)
public class SetupTests
{
    [Fact]
    public void BuildingTable_Has_23_Kinds_And_49_Cards()
    {
        Assert.Equal(23, Buildings.All.Length);
        Assert.Equal(49, Buildings.Count.Sum());
        Assert.Equal(16, Buildings.All.Where(b => b.Tier == 1).Sum(b => b.Count));
        Assert.Equal(14, Buildings.All.Where(b => b.Tier == 2).Sum(b => b.Count));
        Assert.Equal(14, Buildings.All.Where(b => b.Tier == 3).Sum(b => b.Count));
        Assert.Equal(5, Buildings.All.Where(b => b.Tier == 4).Sum(b => b.Count));
        Assert.All(Buildings.All.Where(b => b.Large), b => Assert.Equal(2, b.Spaces));
        Assert.Equal(6, Buildings.All.Count(b => b.IsProduction));
    }

    [Fact]
    public void Setup_Matches_Rules_Table()
    {
        var s = Setup.NewGame(7);
        Assert.Equal(new[] { 2, 2, 2 }, s.Coins);
        Assert.Equal(58, GameConstants.TotalColonists);
        Assert.Equal(55, s.BankColonists);
        Assert.Equal(3, s.ShipColonists);
        Assert.Equal(75, s.VpSupply);
        Assert.Equal(new[] { 10, 11, 11, 9, 9 }, s.GoodsSupply);
        Assert.Equal(50, s.GoodsSupply.Sum());
        Assert.Equal(8, s.QuarrySupply);
        Assert.Equal(4, s.FaceUp.Sum());
        Assert.Equal(47, s.Deck.Sum() + s.FaceUp.Sum());
        Assert.Equal(new[] { 9, 10, 11, 9, 8 }, GameConstants.DeckStart);
        Assert.Equal(new[] { 4, 5, 6 }, GameConstants.ShipCapacity);
        Assert.Equal(Phase.ChooseRole, s.Phase);
        Assert.Equal(0, s.Governor);
        Assert.Null(Invariants.Check(s));
    }

    [Fact]
    public void Starting_Plantations_Are_Indigo_Indigo_Corn_Unoccupied()
    {
        var s = Setup.NewGame(7);
        Assert.Equal(1, s.Tiles[0 * 6 + (int)Good.Indigo]);
        Assert.Equal(1, s.Tiles[1 * 6 + (int)Good.Indigo]);
        Assert.Equal(1, s.Tiles[2 * 6 + (int)Good.Corn]);
        for (int p = 0; p < 3; p++)
        {
            Assert.Equal(1, s.TileCount(p));
            Assert.Equal(0, s.ColonistsOnBoard(p));
        }
    }

    [Fact]
    public void Same_Seed_Same_FaceUp_Different_Seed_Usually_Differs()
    {
        Assert.Equal(Setup.NewGame(5).FaceUp, Setup.NewGame(5).FaceUp);
        var variants = Enumerable.Range(0, 20).Select(i => string.Join(",", Setup.NewGame((ulong)i).FaceUp)).Distinct().Count();
        Assert.True(variants > 1);
    }

    [Fact]
    public void Clone_Is_Deep_For_Every_Array_Field()
    {
        var s = Setup.NewGame(3);
        var c = s.Clone();
        foreach (var f in typeof(GameState).GetFields().Where(f => f.FieldType == typeof(int[])))
        {
            var a = (int[])f.GetValue(s)!;
            var b = (int[])f.GetValue(c)!;
            Assert.False(ReferenceEquals(a, b), $"{f.Name} is shared between clones");
            Assert.Equal(a, b);
        }
        c.Coins[0] = 99;
        c.Deck[0] = 0;
        Assert.Equal(2, s.Coins[0]);
    }

    [Fact]
    public void Clones_Evolve_Identically()
    {
        var a = Setup.NewGame(11);
        var b = a.Clone();
        var rng = new Random(1);
        for (int i = 0; i < 400 && !a.IsOver; i++)
        {
            var la = Sc.Legal(a);
            Assert.Equal(la, Sc.Legal(b));
            var act = la[rng.Next(la.Count)];
            Rules.Apply(a, act);
            Rules.Apply(b, act);
        }
        Assert.Equal(a.Coins, b.Coins);
        Assert.Equal(a.FaceUp, b.FaceUp);
        Assert.Equal(a.RngState, b.RngState);
    }
}
