using PuertoRico.Engine.Game;
using Xunit;
using static PuertoRico.Tests.Sc;

namespace PuertoRico.Tests;

// rules.md section 5
public class EndGameTests
{
    [Fact]
    public void End_Flag_Does_Not_Stop_The_Round()
    {
        var s = New();
        s.EndFlags = EndFlags.CityFull;
        Start(s, 0, Role.Craftsman);
        Assert.False(s.IsOver);
        Do(s, A(ActionType.ChooseRole, (int)Role.Trader));
        Assert.False(s.IsOver);
        Do(s, A(ActionType.ChooseRole, (int)Role.Captain));
        Assert.True(s.IsOver);
        Assert.Equal(Phase.GameOver, s.Phase);
    }

    [Fact]
    public void Governor_Rotates_And_Unchosen_Roles_Get_A_Coin_Each_Round()
    {
        var s = New();
        Start(s, 0, Role.Craftsman);
        FinishRoundWithIdleRoles(s);
        Assert.Equal(2, s.Round);
        Assert.Equal(1, s.Governor);
        Assert.Equal(1, s.Actor);
        Assert.Equal(1, s.RoleCoins[(int)Role.Settler]);
        Assert.Equal(1, s.RoleCoins[(int)Role.Mayor]);
        Assert.Equal(1, s.RoleCoins[(int)Role.Builder]);
        Assert.Equal(0, s.RoleCoins[(int)Role.Craftsman]);
        Assert.All(s.RoleOwner, o => Assert.Equal(-1, o));
    }

    [Fact]
    public void Choosing_A_Role_With_Coins_Collects_Them_All()
    {
        var s = New();
        s.RoleCoins[(int)Role.Builder] = 3;
        int before = s.Coins[0];
        Start(s, 0, Role.Builder);
        Assert.Equal(before + 3, s.Coins[0]);
        Assert.Equal(0, s.RoleCoins[(int)Role.Builder]);
    }

    [Fact]
    public void Round_Limit_Ends_The_Game_With_Scoring()
    {
        var s = Setup.NewGame(1, maxRounds: 1);
        Start(s, 0, Role.Craftsman);
        FinishRoundWithIdleRoles(s);
        Assert.True(s.IsOver);
        Assert.Equal(EndFlags.RoundLimit, s.EndFlags);
        Assert.Equal(3, Scoring.Score(s).Players.Length);
    }

    [Fact]
    public void Seats_Stay_Fixed_While_Governor_Moves()
    {
        var s = New();
        Start(s, 0, Role.Craftsman);
        FinishRoundWithIdleRoles(s);
        Assert.Equal(1, s.Tiles[1 * 6 + (int)Good.Indigo]); // seat 1 still has its starting indigo
        Assert.Equal(1, s.Tiles[2 * 6 + (int)Good.Corn]);
    }
}

public class ScoringTests
{
    private static int Bonus(GameState s, int seat = 0) => Scoring.Score(s).Players[seat].BonusPoints;

    [Fact]
    public void Base_Building_Vp_Count_Without_Colonists_Large_Bonus_Does_Not()
    {
        var s = New();
        Own(s, 0, BuildingId.GuildHall, 0);
        Own(s, 0, BuildingId.SmallIndigoPlant, 0);
        var p = Scoring.Score(s).Players[0];
        Assert.Equal(4 + 1, p.BuildingPoints);
        Assert.Equal(0, p.BonusPoints);
    }

    [Fact]
    public void GuildHall_Counts_Small_One_Large_Two_Only_Production()
    {
        var s = New();
        Own(s, 0, BuildingId.GuildHall, 1);
        Own(s, 0, BuildingId.SmallIndigoPlant);
        Own(s, 0, BuildingId.SmallSugarMill);
        Own(s, 0, BuildingId.LargeSugarMill);
        Own(s, 0, BuildingId.TobaccoStorage);
        Own(s, 0, BuildingId.CoffeeRoaster);
        Own(s, 0, BuildingId.SmallMarket); // violet: ignored
        Assert.Equal(1 + 1 + 2 + 2 + 2, Bonus(s));
    }

    [Theory]
    [InlineData(3, 4)]
    [InlineData(9, 4)]
    [InlineData(10, 5)]
    [InlineData(11, 6)]
    [InlineData(12, 7)]
    public void Residence_Counts_All_Tiles_Occupied_Or_Not(int tiles, int vp)
    {
        var s = New();
        Own(s, 0, BuildingId.Residence, 1);
        s.Tiles[0 * 6 + (int)Good.Indigo] = 0;
        SetTiles(s, 0, (int)Good.Corn, tiles - 2);
        SetTiles(s, 0, (int)Good.Sugar, 2);
        Assert.Equal(vp, Bonus(s));
    }

    [Fact]
    public void Fortress_Counts_All_Colonists_Including_San_Juan_Divided_By_Three()
    {
        var s = New();
        Own(s, 0, BuildingId.Fortress, 1);
        s.SanJuan[0] = 2;
        SetTiles(s, 0, (int)Good.Corn, 3, occupied: 3);
        Own(s, 0, BuildingId.SmallMarket, 1); // total 1 + 2 + 3 + 1 = 7
        Assert.Equal(2, Bonus(s));
    }

    [Fact]
    public void CustomsHouse_Counts_Chips_Only()
    {
        var s = New();
        Own(s, 0, BuildingId.CustomsHouse, 1);
        s.VpChips[0] = 11;
        Assert.Equal(2, Bonus(s));
    }

    [Fact]
    public void CityHall_Counts_Violet_Buildings_Including_Itself()
    {
        var s = New();
        Own(s, 0, BuildingId.CityHall, 1);
        Own(s, 0, BuildingId.SmallMarket);
        Own(s, 0, BuildingId.Hacienda);
        Own(s, 0, BuildingId.SmallIndigoPlant); // production: not violet
        Assert.Equal(3, Bonus(s));
    }

    [Fact]
    public void Unoccupied_Large_Building_Gives_No_Bonus()
    {
        var s = New();
        Own(s, 0, BuildingId.CityHall, 0);
        Own(s, 0, BuildingId.Fortress, 0);
        Assert.Equal(0, Bonus(s));
    }

    [Fact]
    public void Tiebreak_Is_Coins_Plus_Goods_And_Full_Tie_Shares_The_Win()
    {
        var s = New();
        s.VpChips[0] = 10; s.VpChips[1] = 10; s.VpChips[2] = 3;
        s.Coins[0] = 3; s.Coins[1] = 2;
        SetGoods(s, 1, (int)Good.Corn, 1); // seat 1: 2 coins + 1 good = 3 = seat 0's 3 coins
        var score = Scoring.Score(s);
        Assert.Equal(new[] { 0, 1 }, score.Winners);
        Assert.Equal(new[] { 1, 1, 3 }, score.Players.Select(p => p.Rank));

        s.Coins[1] = 3; // now seat 1 has 4
        score = Scoring.Score(s);
        Assert.Equal(new[] { 1 }, score.Winners);
        Assert.Equal(1, score.Players[1].Rank);
        Assert.Equal(2, score.Players[0].Rank);
    }
}
