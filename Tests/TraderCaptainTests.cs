using PuertoRico.Engine.Game;
using Xunit;
using static PuertoRico.Tests.Sc;

namespace PuertoRico.Tests;

// rules.md section 4 (Trader, Captain, Wharf, storage, ship clearing)
public class TraderTests
{
    [Fact]
    public void Price_Is_Base_Plus_Markets_Plus_Chooser_Privilege()
    {
        var s = New();
        Own(s, 1, BuildingId.SmallMarket, 1);
        Own(s, 1, BuildingId.LargeMarket, 1);
        Own(s, 0, BuildingId.LargeMarket, 0); // unoccupied: no bonus
        Start(s, 0, Role.Trader);
        Assert.Equal(0 + 1, Rules.SalePrice(s, 0, (int)Good.Corn));      // chooser +1
        Assert.Equal(4 + 1, Rules.SalePrice(s, 0, (int)Good.Coffee));
        Assert.Equal(1 + 1 + 2, Rules.SalePrice(s, 1, (int)Good.Indigo)); // +1 small, +2 large
        Assert.Equal(2, Rules.SalePrice(s, 2, (int)Good.Sugar));
    }

    [Fact]
    public void Corn_Can_Be_Sold_For_Nothing_And_Takes_A_Slot()
    {
        var s = New();
        SetGoods(s, 1, (int)Good.Corn, 2);
        Start(s, 0, Role.Trader); // seat 0 has no goods -> skipped, seat 1 to act
        Assert.Equal(1, s.Actor);
        int coins = s.Coins[1];
        Do(s, A(ActionType.Sell, (int)Good.Corn));
        Assert.Equal(coins, s.Coins[1]);
        Assert.Equal(1, s.TradeCount);
    }

    [Fact]
    public void Same_Good_Blocked_Unless_Office_And_Pass_Is_Allowed()
    {
        var s = New();
        SetGoods(s, 0, (int)Good.Indigo, 1);
        SetGoods(s, 1, (int)Good.Indigo, 1);
        SetGoods(s, 2, (int)Good.Indigo, 1);
        Start(s, 0, Role.Trader);
        Assert.True(Has(Legal(s), ActionType.Pass));
        Do(s, A(ActionType.Sell, (int)Good.Indigo));
        Assert.Equal(2 + 1 + 1, s.Coins[0]); // indigo 1 + chooser privilege 1
        // seats 1 and 2 hold indigo but cannot sell it (already in the house, no Office): both skipped
        Assert.Equal(Phase.ChooseRole, s.Phase);
        Assert.Equal(1, s.TradeCount);
    }

    [Fact]
    public void Office_Allows_Selling_A_Good_Already_In_The_House()
    {
        var s = New();
        SetGoods(s, 0, (int)Good.Indigo, 1);
        SetGoods(s, 2, (int)Good.Indigo, 1);
        Own(s, 2, BuildingId.Office, 1);
        Start(s, 0, Role.Trader);
        Do(s, A(ActionType.Sell, (int)Good.Indigo));
        Assert.Equal(2, s.Actor);
        Assert.True(Has(Legal(s), ActionType.Sell, (int)Good.Indigo));
    }

    [Fact]
    public void House_Is_Emptied_Only_If_Full_At_The_End_Of_The_Phase()
    {
        var s = New();
        s.TradeHouse[0] = (int)Good.Indigo; s.TradeHouse[1] = (int)Good.Sugar; s.TradeHouse[2] = (int)Good.Tobacco;
        s.TradeCount = 3;
        s.GoodsSupply[(int)Good.Indigo]--; s.GoodsSupply[(int)Good.Sugar]--; s.GoodsSupply[(int)Good.Tobacco]--;
        SetGoods(s, 0, (int)Good.Coffee, 1); s.GoodsSupply[(int)Good.Coffee]--;
        Start(s, 0, Role.Trader);
        Do(s, A(ActionType.Sell, (int)Good.Coffee));
        Assert.Equal(0, s.TradeCount);
        Assert.Null(Invariants.Check(s));

        var t = New();
        SetGoods(t, 0, (int)Good.Coffee, 1); t.GoodsSupply[(int)Good.Coffee]--;
        Start(t, 0, Role.Trader);
        Do(t, A(ActionType.Sell, (int)Good.Coffee));
        Assert.Equal(1, t.TradeCount); // not full: goods stay for the next round
    }
}

public class CaptainTests
{
    private static GameState WithSeat0Goods(params (Good g, int n)[] goods)
    {
        var s = New();
        foreach (var (g, n) in goods) { SetGoods(s, 0, (int)g, n); s.GoodsSupply[(int)g] -= n; }
        return s;
    }

    [Fact]
    public void Loading_Is_Compulsory_No_Pass()
    {
        var s = WithSeat0Goods((Good.Corn, 2));
        Start(s, 0, Role.Captain);
        var legal = Legal(s);
        Assert.False(Has(legal, ActionType.Pass));
        Assert.Equal(3, legal.Count(a => a.Type == ActionType.LoadShip)); // any of the three empty ships
    }

    [Fact]
    public void Loads_As_Many_As_Possible_And_Pays_One_Vp_Per_Barrel_Plus_Privilege()
    {
        var s = WithSeat0Goods((Good.Corn, 9));
        Start(s, 0, Role.Captain);
        Do(s, A(ActionType.LoadShip, (int)Good.Corn, 1)); // ship 1: capacity 5
        Assert.Equal(5, s.ShipLoad[1]);
        Assert.Equal(4, s.Goods[0 * G + (int)Good.Corn]);
        Assert.Equal(5 + 1, s.VpChips[0]); // privilege on the first shipment
        Assert.Equal(75 - 6, s.VpSupply);
    }

    [Fact]
    public void A_Good_Already_On_A_Ship_Must_Go_To_That_Ship_Until_Full()
    {
        var s = WithSeat0Goods((Good.Indigo, 5));
        s.ShipGood[0] = (int)Good.Indigo; s.ShipLoad[0] = 1; s.GoodsSupply[(int)Good.Indigo] -= 1;
        Start(s, 0, Role.Captain);
        var legal = Legal(s);
        Assert.Single(legal);
        Assert.Equal(A(ActionType.LoadShip, (int)Good.Indigo, 0), legal[0]);
        Do(s, legal[0]);
        Assert.Equal(4, s.ShipLoad[0]);
        Assert.Equal(2, s.Goods[0 * G + (int)Good.Indigo]);
        // ship 0 is now full: the remaining indigo cannot go to an empty ship; the phase moves to storage
    }

    [Fact]
    public void Full_Ship_Blocks_The_Same_Good_On_Other_Ships()
    {
        var s = WithSeat0Goods((Good.Indigo, 2));
        s.ShipGood[0] = (int)Good.Indigo; s.ShipLoad[0] = 4; s.GoodsSupply[(int)Good.Indigo] -= 4;
        Start(s, 0, Role.Captain);
        Assert.NotEqual(Phase.Captain, s.Phase); // nothing could be loaded by anyone
    }

    [Fact]
    public void Wharf_Ships_Everything_Of_One_Good_And_Returns_It_To_Supply()
    {
        var s = WithSeat0Goods((Good.Corn, 7));
        Own(s, 0, BuildingId.Wharf, 1);
        Start(s, 0, Role.Captain);
        Assert.True(Has(Legal(s), ActionType.LoadWharf, (int)Good.Corn));
        Do(s, A(ActionType.LoadWharf, (int)Good.Corn));
        Assert.Equal(0, s.Goods[0 * G + (int)Good.Corn]);
        Assert.Equal(10, s.GoodsSupply[(int)Good.Corn]);
        Assert.Equal(7 + 1, s.VpChips[0]);
        Assert.Equal(1, s.WharfUsed[0]);
        Assert.Null(Invariants.Check(s));
    }

    [Fact]
    public void Harbor_Stacks_With_Captain_Privilege_On_First_Shipment_Only()
    {
        var s = WithSeat0Goods((Good.Corn, 2), (Good.Sugar, 1));
        Own(s, 0, BuildingId.Harbor, 1);
        Start(s, 0, Role.Captain);
        Do(s, A(ActionType.LoadShip, (int)Good.Corn, 0));
        Assert.Equal(2 + 1 + 1, s.VpChips[0]); // barrels + Harbor + privilege
        Do(s, A(ActionType.LoadShip, (int)Good.Sugar, 1));
        Assert.Equal(4 + 1 + 1, s.VpChips[0]);  // barrel + Harbor only
    }

    [Fact]
    public void Chips_Run_Out_Is_Still_Paid_And_Flags_The_End()
    {
        var s = WithSeat0Goods((Good.Corn, 4));
        s.VpSupply = 3;
        Start(s, 0, Role.Captain);
        Do(s, A(ActionType.LoadShip, (int)Good.Corn, 0));
        Assert.Equal(5, s.VpChips[0]);
        Assert.Equal(0, s.VpSupply);
        Assert.True((s.EndFlags & EndFlags.VpExhausted) != 0);
        Assert.False(s.IsOver);
    }

    private static GameState AllShipsFull()
    {
        var s = New();
        s.ShipGood[0] = (int)Good.Coffee; s.ShipLoad[0] = 4;
        s.ShipGood[1] = (int)Good.Tobacco; s.ShipLoad[1] = 5;
        s.ShipGood[2] = (int)Good.Sugar; s.ShipLoad[2] = 6;
        s.GoodsSupply[(int)Good.Coffee] -= 4; s.GoodsSupply[(int)Good.Tobacco] -= 5; s.GoodsSupply[(int)Good.Sugar] -= 6;
        return s;
    }

    [Fact]
    public void Storage_Without_Warehouse_Keeps_One_Barrel_Of_Choice()
    {
        var s = AllShipsFull();
        SetGoods(s, 0, (int)Good.Corn, 3); SetGoods(s, 0, (int)Good.Indigo, 2);
        s.GoodsSupply[(int)Good.Corn] -= 3; s.GoodsSupply[(int)Good.Indigo] -= 2;
        Start(s, 0, Role.Captain);
        Assert.Equal(Phase.CaptainStorage, s.Phase);
        var legal = Legal(s);
        Assert.All(legal, a => Assert.Equal(ActionType.KeepBarrel, a.Type));
        Assert.Equal(2, legal.Count);
        Do(s, A(ActionType.KeepBarrel, (int)Good.Indigo));
        Assert.Equal(1, s.Goods[0 * G + (int)Good.Indigo]);
        Assert.Equal(0, s.Goods[0 * G + (int)Good.Corn]);
        Assert.Equal(10, s.GoodsSupply[(int)Good.Corn]);
        Assert.Null(Invariants.Check(s));
    }

    [Fact]
    public void Small_Warehouse_Keeps_One_Whole_Kind_Plus_One_Barrel()
    {
        var s = AllShipsFull();
        Own(s, 0, BuildingId.SmallWarehouse, 1);
        SetGoods(s, 0, (int)Good.Corn, 3); SetGoods(s, 0, (int)Good.Indigo, 2); SetGoods(s, 0, (int)Good.Tobacco, 0);
        s.GoodsSupply[(int)Good.Corn] -= 3; s.GoodsSupply[(int)Good.Indigo] -= 2;
        Start(s, 0, Role.Captain);
        Assert.All(Legal(s), a => Assert.Equal(ActionType.KeepGoods, a.Type));
        Do(s, A(ActionType.KeepGoods, (int)Good.Corn));
        // the other kind: one barrel (single choice, still asked)
        Assert.Equal(new[] { A(ActionType.KeepBarrel, (int)Good.Indigo) }, Legal(s));
        Do(s, A(ActionType.KeepBarrel, (int)Good.Indigo));
        Assert.Equal(3, s.Goods[0 * G + (int)Good.Corn]);
        Assert.Equal(1, s.Goods[0 * G + (int)Good.Indigo]);
    }

    [Fact]
    public void Large_Warehouse_Keeps_Two_Kinds_And_Third_Kind_One_Barrel()
    {
        var s = AllShipsFull();
        Own(s, 0, BuildingId.LargeWarehouse, 1);
        SetGoods(s, 0, (int)Good.Corn, 3); SetGoods(s, 0, (int)Good.Indigo, 2); SetGoods(s, 0, (int)Good.Coffee, 0);
        s.Goods[0 * G + (int)Good.Sugar] = 2; // sugar is on a full ship but players may still hold it
        s.GoodsSupply[(int)Good.Corn] -= 3; s.GoodsSupply[(int)Good.Indigo] -= 2; s.GoodsSupply[(int)Good.Sugar] -= 2;
        Start(s, 0, Role.Captain);
        Do(s, A(ActionType.KeepGoods, (int)Good.Corn));
        Do(s, A(ActionType.KeepGoods, (int)Good.Indigo));
        Do(s, A(ActionType.KeepBarrel, (int)Good.Sugar));
        Assert.Equal(new[] { 3, 2, 1 }, new[] { s.Goods[0 * G], s.Goods[0 * G + 1], s.Goods[0 * G + 2] });
    }

    [Fact]
    public void Only_Full_Ships_Are_Emptied_After_The_Phase()
    {
        var s = New();
        s.ShipGood[0] = (int)Good.Coffee; s.ShipLoad[0] = 4;   // full
        s.ShipGood[1] = (int)Good.Tobacco; s.ShipLoad[1] = 2;  // partly full: stays
        s.GoodsSupply[(int)Good.Coffee] -= 4; s.GoodsSupply[(int)Good.Tobacco] -= 2;
        Start(s, 0, Role.Captain); // nobody holds goods: shipping ends at once
        Assert.Equal(0, s.ShipLoad[0]);
        Assert.Equal(-1, s.ShipGood[0]);
        Assert.Equal(2, s.ShipLoad[1]);
        Assert.Equal(9, s.GoodsSupply[(int)Good.Coffee]);
        Assert.Null(Invariants.Check(s));
    }
}
