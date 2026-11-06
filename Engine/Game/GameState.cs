namespace PuertoRico.Engine.Game;

/// <summary>
/// Whole game state. Only numbers and fixed-length arrays (no collections, no strings) so that
/// <see cref="Clone"/> is cheap. Per-player data is flattened: index = seat * stride + item.
/// Seat ids (0..2 = Player 1..3) are fixed; <see cref="Governor"/> rotates separately.
/// </summary>
public sealed class GameState
{
    private const int P = GameConstants.Players;
    private const int G = GameConstants.GoodCount;
    private const int T = GameConstants.TileTypes;
    private const int B = GameConstants.BuildingCount;

    // ---- per player ----
    public int[] Coins = new int[P];
    /// <summary>VP chips held (may exceed the chip supply; the excess is "recorded on paper").</summary>
    public int[] VpChips = new int[P];
    /// <summary>Colonists waiting in San Juan.</summary>
    public int[] SanJuan = new int[P];
    /// <summary>Tiles owned, [seat*6 + type].</summary>
    public int[] Tiles = new int[P * T];
    /// <summary>Occupied tiles, [seat*6 + type].</summary>
    public int[] TilesOcc = new int[P * T];
    /// <summary>1 if the building is owned, [seat*23 + building].</summary>
    public int[] BuildingOwned = new int[P * B];
    /// <summary>Colonists on the building.</summary>
    public int[] BuildingOcc = new int[P * B];
    public int[] Goods = new int[P * G];

    // ---- supplies ----
    public int[] GoodsSupply = new int[G];
    public int[] BuildingSupply = new int[B];
    public int QuarrySupply;
    public int[] Deck = new int[G];
    public int[] Discard = new int[G];
    public int[] FaceUp = new int[G];
    public int BankColonists;
    public int ShipColonists;
    public int VpSupply;
    public int[] RoleCoins = new int[GameConstants.RoleCount];
    /// <summary>Seat that chose each role this round, or -1.</summary>
    public int[] RoleOwner = new int[GameConstants.RoleCount];

    // ---- ships and trading house ----
    public int[] ShipGood = new int[GameConstants.ShipCount];
    public int[] ShipLoad = new int[GameConstants.ShipCount];
    public int[] TradeHouse = new int[GameConstants.TradeSlots];
    public int TradeCount;

    // ---- flow ----
    public Phase Phase;
    /// <summary>Seat that must decide now.</summary>
    public int Actor;
    public int Governor;
    public int Round = 1;
    public int MaxRounds = GameConstants.DefaultMaxRounds;
    /// <summary>Roles chosen so far this round (0..3).</summary>
    public int ChosenCount;
    public int CurrentRole;
    public int CurrentOwner;
    /// <summary>Actors that have finished the current role phase.</summary>
    public int ActorsDone;
    public EndFlags EndFlags;
    public ulong RngState;

    // ---- sub-state of the current phase ----
    public int HaciendaUsed;
    public int MayorLastSlot;
    public int MayorRemain;
    /// <summary>Production computed at the start of Craftsman, [seat*5 + good].</summary>
    public int[] Production = new int[P * G];
    public int CaptainSkips;
    public int CaptainFirstDone;
    public int[] WharfUsed = new int[P];
    public int StoreTarget;
    public int StoreKeptCount;
    public int StoreKeptMask;
    public int StoreLastKept;
    public int StoreBarrel;

    public bool IsOver => Phase == Phase.GameOver;

    public GameState() { }

    public GameState Clone()
    {
        var c = (GameState)MemberwiseClone();
        c.Coins = (int[])Coins.Clone();
        c.VpChips = (int[])VpChips.Clone();
        c.SanJuan = (int[])SanJuan.Clone();
        c.Tiles = (int[])Tiles.Clone();
        c.TilesOcc = (int[])TilesOcc.Clone();
        c.BuildingOwned = (int[])BuildingOwned.Clone();
        c.BuildingOcc = (int[])BuildingOcc.Clone();
        c.Goods = (int[])Goods.Clone();
        c.GoodsSupply = (int[])GoodsSupply.Clone();
        c.BuildingSupply = (int[])BuildingSupply.Clone();
        c.Deck = (int[])Deck.Clone();
        c.Discard = (int[])Discard.Clone();
        c.FaceUp = (int[])FaceUp.Clone();
        c.RoleCoins = (int[])RoleCoins.Clone();
        c.RoleOwner = (int[])RoleOwner.Clone();
        c.ShipGood = (int[])ShipGood.Clone();
        c.ShipLoad = (int[])ShipLoad.Clone();
        c.TradeHouse = (int[])TradeHouse.Clone();
        c.Production = (int[])Production.Clone();
        c.WharfUsed = (int[])WharfUsed.Clone();
        return c;
    }

    // ---- helpers ----
    public int TileCount(int seat) { int n = 0; for (int t = 0; t < T; t++) n += Tiles[seat * T + t]; return n; }

    public int CitySpacesUsed(int seat)
    {
        int n = 0;
        for (int b = 0; b < B; b++) if (BuildingOwned[seat * B + b] != 0) n += Buildings.Spaces[b];
        return n;
    }

    /// <summary>True if the building is owned and has at least one colonist ("occupied").</summary>
    public bool HasOccupied(int seat, BuildingId id) =>
        BuildingOwned[seat * B + (int)id] != 0 && BuildingOcc[seat * B + (int)id] > 0;

    public bool Owns(int seat, BuildingId id) => BuildingOwned[seat * B + (int)id] != 0;

    public int GoodTotal(int seat) { int n = 0; for (int g = 0; g < G; g++) n += Goods[seat * G + g]; return n; }

    public int DeckTotal() { int n = 0; for (int g = 0; g < G; g++) n += Deck[g]; return n; }
    public int DiscardTotal() { int n = 0; for (int g = 0; g < G; g++) n += Discard[g]; return n; }

    /// <summary>Total colonists the seat has anywhere on its board (including San Juan).</summary>
    public int ColonistsOnBoard(int seat)
    {
        int n = SanJuan[seat];
        for (int t = 0; t < T; t++) n += TilesOcc[seat * T + t];
        for (int b = 0; b < B; b++) n += BuildingOcc[seat * B + b];
        return n;
    }

    /// <summary>Re-seed the random generator (MCTS rollouts must do this after cloning).</summary>
    public void ReseedRng(ulong seed) => RngState = seed;
}
