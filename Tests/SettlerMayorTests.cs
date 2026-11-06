using PuertoRico.Engine.Game;
using Xunit;
using static PuertoRico.Tests.Sc;

namespace PuertoRico.Tests;

// rules.md section 1 (tile pile), section 4 (Settler, Hacienda, Hospice, Mayor)
public class SettlerTests
{
    [Fact]
    public void Quarry_Only_For_Chooser_Or_Occupied_ConstructionHut()
    {
        var s = New();
        Own(s, 1, BuildingId.ConstructionHut, occupied: 1);
        Own(s, 2, BuildingId.ConstructionHut, occupied: 0); // unoccupied: no effect
        Start(s, 0, Role.Settler);
        Assert.True(Has(Legal(s), ActionType.TakeQuarry));
        Do(s, GameAction.Pass);
        Assert.Equal(1, s.Actor);
        Assert.True(Has(Legal(s), ActionType.TakeQuarry));
        Do(s, GameAction.Pass);
        Assert.Equal(2, s.Actor);
        Assert.False(Has(Legal(s), ActionType.TakeQuarry));
    }

    [Fact]
    public void Pass_Is_Always_Legal_And_Taking_A_Quarry_Leaves_FaceUp_Untouched()
    {
        var s = New();
        Start(s, 0, Role.Settler);
        Assert.True(Has(Legal(s), ActionType.Pass));
        var before = (int[])s.FaceUp.Clone();
        Do(s, A(ActionType.TakeQuarry));
        Assert.Equal(before, s.FaceUp);
        Assert.Equal(7, s.QuarrySupply);
        Assert.Equal(1, s.Tiles[0 * 6 + GameConstants.QuarryType]);
    }

    [Fact]
    public void Full_Island_Cannot_Act_And_Is_Skipped()
    {
        var s = New();
        SetTiles(s, 1, (int)Good.Corn, 12);
        Start(s, 0, Role.Settler);
        Do(s, GameAction.Pass);
        Assert.Equal(2, s.Actor); // seat 1 skipped
    }

    [Fact]
    public void Hacienda_Is_Optional_Once_Per_Turn_And_Fills_The_Last_Space()
    {
        var s = New();
        Own(s, 0, BuildingId.Hacienda, 1);
        Start(s, 0, Role.Settler);
        Assert.True(Has(Legal(s), ActionType.UseHacienda));
        int deck = s.DeckTotal();
        Do(s, A(ActionType.UseHacienda));
        Assert.Equal(deck - 1, s.DeckTotal());
        Assert.Equal(2, s.TileCount(0));
        Assert.Equal(0, s.Actor);
        Assert.False(Has(Legal(s), ActionType.UseHacienda));
        Assert.True(Has(Legal(s), ActionType.TakePlantation));

        // with 11 tiles, the Hacienda tile makes 12 -> no face-up tile may be taken afterwards
        var t = New();
        Own(t, 0, BuildingId.Hacienda, 1);
        SetTiles(t, 0, (int)Good.Corn, 10);
        Start(t, 0, Role.Settler);
        Do(t, A(ActionType.UseHacienda));
        Assert.Equal(12, t.TileCount(0));
        Assert.Equal(1, t.Actor); // turn ended automatically
    }

    [Fact]
    public void Full_Island_Cannot_Use_Hacienda()
    {
        var s = New();
        Own(s, 0, BuildingId.Hacienda, 1);
        SetTiles(s, 0, (int)Good.Corn, 12);
        Start(s, 0, Role.Settler);
        Assert.Equal(1, s.Actor);
    }

    [Fact]
    public void Hospice_Gives_Colonist_From_Bank_Then_Ship_Then_Nothing()
    {
        int FaceUpType(GameState x) => Enumerable.Range(0, 5).First(g => x.FaceUp[g] > 0);

        var s = New();
        Own(s, 0, BuildingId.Hospice, 1);
        Start(s, 0, Role.Settler);
        int g = FaceUpType(s);
        Do(s, A(ActionType.TakePlantation, g));
        Assert.Equal(1, s.TilesOcc[0 * 6 + g]);
        Assert.Equal(53, s.BankColonists); // 55 - 1 (hospice occupant) - 1

        var t = New();
        Own(t, 0, BuildingId.Hospice, 1);
        t.BankColonists = 0;
        Start(t, 0, Role.Settler);
        g = FaceUpType(t);
        Do(t, A(ActionType.TakePlantation, g));
        Assert.Equal(1, t.TilesOcc[0 * 6 + g]);
        Assert.Equal(2, t.ShipColonists); // fell back to the colonist ship

        var u = New();
        Own(u, 0, BuildingId.Hospice, 1);
        u.BankColonists = 0;
        u.ShipColonists = 0;
        Start(u, 0, Role.Settler);
        g = FaceUpType(u);
        Do(u, A(ActionType.TakePlantation, g));
        Assert.Equal(0, u.TilesOcc[0 * 6 + g]);
    }

    [Fact]
    public void Hacienda_Tile_Also_Triggers_Hospice()
    {
        var s = New();
        Own(s, 0, BuildingId.Hacienda, 1);
        Own(s, 0, BuildingId.Hospice, 1);
        Start(s, 0, Role.Settler);
        Do(s, A(ActionType.UseHacienda));
        int g = Enumerable.Range(0, 5).First(x => s.FaceUp[x] > 0);
        Do(s, A(ActionType.TakePlantation, g));
        Assert.Equal(3, s.TileCount(0));
        Assert.Equal(2, s.TilesOcc.Skip(0).Take(6).Sum()); // two new tiles, two colonists
    }

    [Fact]
    public void Unclaimed_FaceUp_Are_Discarded_And_Four_New_Turned_Up_After_Settler()
    {
        var s = New();
        Start(s, 0, Role.Settler);
        PassUntil(s, Phase.Settler);
        Assert.Equal(4, s.Discard.Sum());
        Assert.Equal(4, s.FaceUp.Sum());
        Assert.Equal(47 - 8, s.Deck.Sum());
        Assert.Null(Invariants.Check(s));
    }

    [Fact]
    public void Pile_Runs_Out_Then_Discard_Is_Reshuffled()
    {
        var s = New();
        Array.Clear(s.Deck);
        s.Deck[(int)Good.Corn] = 2;
        s.Discard[(int)Good.Sugar] = 10;
        Start(s, 0, Role.Settler);
        PassUntil(s, Phase.Settler);
        // 4 face-up went to discard (14 total), pile had 2 -> reshuffled 14 and drew the other 2
        Assert.Equal(4, s.FaceUp.Sum());
        Assert.Equal(12, s.Deck.Sum());
    }

    [Fact]
    public void No_Settler_This_Round_Keeps_FaceUp_Unchanged()
    {
        var s = New();
        var before = (int[])s.FaceUp.Clone();
        Start(s, 0, Role.Craftsman);
        Assert.False(s.Phase == Phase.CraftsmanBonus);
        FinishRoundWithIdleRoles(s);
        Assert.Equal(2, s.Round);
        Assert.Equal(before, s.FaceUp);
        Assert.Equal(0, s.Discard.Sum());
    }
}

public class MayorTests
{
    [Fact]
    public void Privilege_Colonist_Comes_From_Bank_Not_Ship()
    {
        var s = New();
        s.BankColonists = 0; s.ShipColonists = 3; // nothing in the bank: privilege is lost
        Start(s, 0, Role.Mayor);
        Assert.Equal(3, s.SanJuan.Sum() + s.TilesOcc.Sum()); // only the ship's 3, distributed
        Assert.Equal(0, s.ShipColonists);
    }

    [Fact]
    public void Ship_Is_Distributed_One_By_One_Starting_With_Mayor()
    {
        var s = New();
        s.ShipColonists = 7;
        Start(s, 1, Role.Mayor);
        // 1 privilege + 7: Mayor (seat 1) 1 + 3, seat 2 gets 3 (rounds), seat 0 gets 2 -> 4,3,2... check totals
        int total(int seat) => s.ColonistsOnBoard(seat);
        Assert.Equal(8, total(0) + total(1) + total(2));
        Assert.Equal(1 + 3, total(1));
        Assert.Equal(2, total(2));
        Assert.Equal(2, total(0));
    }

    [Fact]
    public void Colonists_Must_Fill_All_Circles_And_Extra_Stay_In_San_Juan()
    {
        var s = New();
        s.ShipColonists = 5; // seat 0: 1 (privilege) + 2 -> 3 colonists, only 1 circle (its indigo plantation)
        Start(s, 0, Role.Mayor);
        var legal = Legal(s);
        Assert.Single(legal);
        Assert.Equal(A(ActionType.PlaceColonist, (int)Good.Indigo), legal[0]);
        Do(s, legal[0]);
        Assert.Equal(2, s.SanJuan[0]);
        Assert.Equal(1, s.TilesOcc[0 * 6 + (int)Good.Indigo]);
        Assert.Equal(1, s.Actor);
    }

    [Fact]
    public void Placement_Is_Canonical_Each_Distribution_Has_One_Action_Sequence()
    {
        var s = New();
        Own(s, 0, BuildingId.SmallIndigoPlant);
        Own(s, 0, BuildingId.SmallSugarMill);
        s.ShipColonists = 1; // seat 0 gets privilege + 1 = 2 colonists, 3 free circles
        Start(s, 0, Role.Mayor);
        var outcomes = new List<string>();
        void Walk(GameState st, string path)
        {
            if (st.Actor != 0 || st.Phase != Phase.Mayor) { outcomes.Add(path); return; }
            foreach (var a in Legal(st))
            {
                var c = st.Clone();
                Do(c, a);
                Walk(c, path + a + ";");
            }
        }
        Walk(s, "");
        Assert.Equal(3, outcomes.Count);            // C(3,2) distributions
        Assert.Equal(3, outcomes.Distinct().Count());
    }

    [Fact]
    public void Colonists_Can_Be_Rearranged_Freely()
    {
        var s = New();
        Own(s, 0, BuildingId.SmallIndigoPlant, occupied: 1);
        SetTiles(s, 0, (int)Good.Indigo, 1, occupied: 1);
        s.BankColonists += 0;
        s.ShipColonists = 0;
        s.BankColonists = 0;
        Start(s, 0, Role.Mayor); // no privilege (bank empty), nothing on the ship
        // seat 0 has 2 colonists on board and 2 circles: both slots must be refilled, in order
        var legal = Legal(s);
        Assert.Single(legal); // both circles must be filled, canonical order: plantation first
        Do(s, legal[0]);
        Do(s, Legal(s)[0]);
        Assert.Equal(2, s.TilesOcc[0 * 6 + (int)Good.Indigo] + s.BuildingOcc[0 * Sc.B + (int)BuildingId.SmallIndigoPlant]);
    }

    [Fact]
    public void Refill_Is_Max_Of_Empty_Building_Circles_And_Players()
    {
        var s = New();
        s.ShipColonists = 0;
        Own(s, 2, BuildingId.LargeSugarMill); // 3 empty circles
        Own(s, 2, BuildingId.CoffeeRoaster);   // 2 more
        Own(s, 1, BuildingId.GuildHall);       // 1 more (violet counts too); tiles never count
        s.BankColonists = 30;
        Start(s, 0, Role.Mayor);               // privilege 1: bank 29, seat 0 places it on its plantation
        for (int i = 0; i < 3; i++) if (s.Phase == Phase.Mayor) Do(s, Legal(s)[0]);
        Assert.Equal(6, s.ShipColonists);
        Assert.Equal(23, s.BankColonists);
    }

    [Fact]
    public void Refill_Has_A_Floor_Of_Three()
    {
        var s = New();
        s.ShipColonists = 0;
        Start(s, 0, Role.Mayor);
        while (s.Phase == Phase.Mayor) Do(s, Legal(s)[0]);
        Assert.Equal(3, s.ShipColonists);
    }

    [Fact]
    public void Short_Supply_Triggers_End_Only_When_Strictly_Less_Than_Needed()
    {
        var exact = New();
        exact.ShipColonists = 0;
        exact.BankColonists = 4; // privilege takes 1 -> 3 left == need 3 -> fine
        Start(exact, 0, Role.Mayor);
        while (exact.Phase == Phase.Mayor) Do(exact, Legal(exact)[0]);
        Assert.Equal(EndFlags.None, exact.EndFlags);
        Assert.Equal(3, exact.ShipColonists);

        var shortage = New();
        shortage.ShipColonists = 0;
        shortage.BankColonists = 3; // 2 left < 3
        Start(shortage, 0, Role.Mayor);
        while (shortage.Phase == Phase.Mayor) Do(shortage, Legal(shortage)[0]);
        Assert.Equal(EndFlags.ColonistsShort, shortage.EndFlags);
        Assert.Equal(2, shortage.ShipColonists);
        Assert.Equal(0, shortage.BankColonists);
        Assert.False(shortage.IsOver); // the round still has to finish
    }
}
