using PuertoRico.Engine.Game;
using Xunit;
using static PuertoRico.Tests.Sc;

namespace PuertoRico.Tests;

// rules.md section 3 (discounts), section 4 (Builder, University, Craftsman)
public class BuilderTests
{
    [Fact]
    public void Cost_Uses_Occupied_Quarries_Up_To_Tier_Cap_Plus_Privilege()
    {
        var s = New();
        SetTiles(s, 0, GameConstants.QuarryType, 2, occupied: 2);
        SetTiles(s, 1, GameConstants.QuarryType, 3, occupied: 3);
        SetTiles(s, 2, GameConstants.QuarryType, 3, occupied: 0); // unoccupied quarries give nothing
        Start(s, 0, Role.Builder);
        int sugarMill = (int)BuildingId.LargeSugarMill; // cost 4, tier 2
        Assert.Equal(1, Rules.BuildingCost(s, 0, sugarMill)); // 4 - 2 - 1
        Assert.Equal(2, Rules.BuildingCost(s, 1, sugarMill)); // 4 - min(3,2)
        Assert.Equal(4, Rules.BuildingCost(s, 2, sugarMill));
        Assert.Equal(7 - 3, Rules.BuildingCost(s, 1, (int)BuildingId.Factory)); // tier 3 cap 3
        Assert.Equal(10 - 3, Rules.BuildingCost(s, 1, (int)BuildingId.CityHall)); // tier 4 but only 3 quarries
    }

    [Fact]
    public void Cost_Never_Goes_Below_Zero()
    {
        var s = New();
        SetTiles(s, 0, GameConstants.QuarryType, 1, occupied: 1);
        Start(s, 0, Role.Builder);
        Assert.Equal(0, Rules.BuildingCost(s, 0, (int)BuildingId.SmallIndigoPlant)); // 1 - 1 - 1
        Assert.Equal(1, Rules.BuildingCost(s, 1, (int)BuildingId.SmallIndigoPlant)); // no quarry, not the Builder
    }

    [Fact]
    public void Cannot_Buy_A_Building_You_Already_Own_Or_Cannot_Afford()
    {
        var s = New();
        Own(s, 0, BuildingId.SmallMarket);
        Start(s, 0, Role.Builder);
        var legal = Legal(s);
        Assert.False(Has(legal, ActionType.Build, (int)BuildingId.SmallMarket));
        Assert.True(Has(legal, ActionType.Build, (int)BuildingId.SmallIndigoPlant)); // owner pays 0
        Assert.False(Has(legal, ActionType.Build, (int)BuildingId.Factory)); // cost 6 for owner, has 2
        Assert.True(Has(legal, ActionType.Pass));
    }

    [Fact]
    public void Large_Building_Needs_Two_Free_City_Spaces()
    {
        var s = New();
        var ones = Buildings.All.Where(b => b.Spaces == 1 && b.Id != BuildingId.Wharf).Take(11).ToList();
        foreach (var b in ones) Own(s, 0, b.Id);
        s.Coins[0] = 50;
        Start(s, 0, Role.Builder);
        var legal = Legal(s);
        Assert.False(Has(legal, ActionType.Build, (int)BuildingId.GuildHall));
        Assert.True(Has(legal, ActionType.Build, (int)BuildingId.Wharf));
    }

    [Fact]
    public void Full_City_Can_Only_Pass_And_Triggers_End_After_The_Round()
    {
        var s = New();
        foreach (var b in Buildings.All.Where(b => b.Spaces == 1).Take(12)) Own(s, 1, b.Id);
        Start(s, 0, Role.Builder);
        PassUntil(s, Phase.Builder);
        Assert.Equal(EndFlags.CityFull, s.EndFlags);
        Assert.False(s.IsOver);
        FinishRoundWithIdleRoles(s);
        Assert.True(s.IsOver);
    }

    [Fact]
    public void University_Places_A_Colonist_On_The_New_Building_Bank_Then_Ship()
    {
        var s = New();
        Own(s, 0, BuildingId.University, occupied: 1);
        s.Coins[0] = 5;
        Start(s, 0, Role.Builder);
        int bank = s.BankColonists;
        Do(s, A(ActionType.Build, (int)BuildingId.SmallMarket));
        Assert.Equal(1, s.BuildingOcc[0 * B + (int)BuildingId.SmallMarket]);
        Assert.Equal(bank - 1, s.BankColonists);

        var t = New();
        Own(t, 0, BuildingId.University, occupied: 1);
        t.Coins[0] = 5;
        t.BankColonists = 0;
        Start(t, 0, Role.Builder);
        Do(t, A(ActionType.Build, (int)BuildingId.SmallMarket));
        Assert.Equal(1, t.BuildingOcc[0 * B + (int)BuildingId.SmallMarket]);
        Assert.Equal(2, t.ShipColonists);

        var u = New();
        Own(u, 0, BuildingId.University, occupied: 1);
        u.Coins[0] = 5;
        u.BankColonists = 0; u.ShipColonists = 0;
        Start(u, 0, Role.Builder);
        Do(u, A(ActionType.Build, (int)BuildingId.SmallMarket));
        Assert.Equal(0, u.BuildingOcc[0 * B + (int)BuildingId.SmallMarket]);
    }

    [Fact]
    public void Unoccupied_University_Does_Nothing()
    {
        var s = New();
        Own(s, 0, BuildingId.University, occupied: 0);
        s.Coins[0] = 5;
        Start(s, 0, Role.Builder);
        Do(s, A(ActionType.Build, (int)BuildingId.SmallMarket));
        Assert.Equal(0, s.BuildingOcc[0 * B + (int)BuildingId.SmallMarket]);
    }

    [Fact]
    public void Paying_Reduces_Coins_And_Supply()
    {
        var s = New();
        s.Coins[0] = 6;
        Start(s, 0, Role.Builder);
        Do(s, A(ActionType.Build, (int)BuildingId.Hospice)); // 4 - 1
        Assert.Equal(3, s.Coins[0]);
        Assert.Equal(1, s.BuildingSupply[(int)BuildingId.Hospice]);
    }
}

public class CraftsmanTests
{
    [Fact]
    public void Production_Formula_Corn_Needs_No_Building_Others_Take_Min()
    {
        var s = New();
        SetTiles(s, 0, (int)Good.Corn, 3, occupied: 2);
        SetTiles(s, 0, (int)Good.Indigo, 3, occupied: 3);
        Own(s, 0, BuildingId.SmallIndigoPlant, 1);
        Own(s, 0, BuildingId.LargeIndigoPlant, 1); // 2 occupied circles
        SetTiles(s, 0, (int)Good.Coffee, 2, occupied: 2); // no roaster
        Assert.Equal(2, Rules.ProductionOf(s, 0, (int)Good.Corn));
        Assert.Equal(2, Rules.ProductionOf(s, 0, (int)Good.Indigo));
        Assert.Equal(0, Rules.ProductionOf(s, 0, (int)Good.Coffee));
        Assert.Equal(0, Rules.ProductionOf(s, 0, (int)Good.Sugar));
    }

    [Fact]
    public void Privilege_Gives_One_Extra_Of_A_Produced_Good()
    {
        var s = New();
        SetTiles(s, 0, (int)Good.Corn, 2, occupied: 2);
        Start(s, 0, Role.Craftsman);
        Assert.Equal(Phase.CraftsmanBonus, s.Phase);
        var legal = Legal(s);
        Assert.Single(legal);
        Assert.Equal(A(ActionType.CraftsmanBonus, (int)Good.Corn), legal[0]);
        Do(s, legal[0]);
        Assert.Equal(3, s.Goods[0 * G + (int)Good.Corn]);
        Assert.Equal(7, s.GoodsSupply[(int)Good.Corn]);
    }

    [Fact]
    public void No_Production_Means_No_Decision()
    {
        var s = New();
        Start(s, 0, Role.Craftsman);
        Assert.Equal(Phase.ChooseRole, s.Phase);
        Assert.Equal(1, s.Actor);
    }

    [Fact]
    public void Short_Supply_Is_Paid_Craftsman_First_Each_Seat_Takes_All_It_Is_Owed()
    {
        var s = New();
        SetTiles(s, 0, (int)Good.Corn, 2, occupied: 2);
        SetTiles(s, 1, (int)Good.Corn, 2, occupied: 2);
        SetTiles(s, 2, (int)Good.Corn, 2, occupied: 2);
        s.GoodsSupply[(int)Good.Corn] = 5;
        Start(s, 1, Role.Craftsman);
        Do(s, A(ActionType.CraftsmanBonus, (int)Good.Corn)); // seat 1 is owed 2 + 1 = 3
        Assert.Equal(3, s.Goods[1 * G]);
        Assert.Equal(2, s.Goods[2 * G]);
        Assert.Equal(0, s.Goods[0 * G]);
        Assert.Equal(0, s.GoodsSupply[(int)Good.Corn]);
    }

    [Fact]
    public void Privilege_Cannot_Create_Goods_Beyond_The_Supply()
    {
        var s = New();
        SetTiles(s, 0, (int)Good.Corn, 1, occupied: 1);
        s.GoodsSupply[(int)Good.Corn] = 1;
        Start(s, 0, Role.Craftsman);
        Do(s, A(ActionType.CraftsmanBonus, (int)Good.Corn)); // wants 2, only 1 exists
        Assert.Equal(1, s.Goods[0]);
        Assert.Equal(0, s.GoodsSupply[(int)Good.Corn]);
    }

    [Fact]
    public void Factory_Pays_By_Number_Of_Kinds_Produced()
    {
        var s = New();
        Own(s, 0, BuildingId.Factory, 1);
        SetTiles(s, 0, (int)Good.Corn, 1, occupied: 1);
        SetTiles(s, 0, (int)Good.Indigo, 1, occupied: 1);
        Own(s, 0, BuildingId.SmallIndigoPlant, 1);
        SetTiles(s, 0, (int)Good.Sugar, 1, occupied: 1);
        Own(s, 0, BuildingId.SmallSugarMill, 1);
        int coins = s.Coins[0];
        Start(s, 0, Role.Craftsman);
        Do(s, Legal(s)[0]);
        Assert.Equal(coins + 2, s.Coins[0]); // 3 kinds -> 2 coins
    }
}
