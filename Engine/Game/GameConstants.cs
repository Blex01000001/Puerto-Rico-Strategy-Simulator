namespace PuertoRico.Engine.Game;

/// <summary>Fixed numbers for the base game (rules.md sections 1 and 7). Single place for setup numbers.</summary>
public static class GameConstants
{
    public const int MinPlayers = 3;
    public const int MaxPlayers = 4;
    public const int GoodCount = 5;
    /// <summary>Tile types: 0..4 = plantation of that good, 5 = quarry.</summary>
    public const int TileTypes = 6;
    public const int QuarryType = 5;
    public const int MaxRoleCount = 7;
    public const int BuildingCount = 23;
    public const int ShipCount = 3;
    public const int TradeSlots = 4;
    public const int MaxTiles = 12;
    public const int CitySpaces = 12;
    public const int QuarryTotal = 8;
    public const int DefaultMaxRounds = 150;

    // ---- depend on the number of players (3 or 4) ----
    public static int RoleCount(int players) => players == 3 ? 6 : 7;
    public static int FaceUpTiles(int players) => players + 1;
    public static int StartCoins(int players) => players == 3 ? 2 : 3;
    public static int TotalColonists(int players) => players == 3 ? 58 : 79;
    public static int StartShipColonists(int players) => players == 3 ? 3 : 4;
    public static int BankColonists(int players) => TotalColonists(players) - StartShipColonists(players);
    public static int VpChips(int players) => players == 3 ? 75 : 100;

    /// <summary>Public ship capacities by number of players: 3 players 4/5/6, 4 players 5/6/7.</summary>
    public static int[] ShipCapacity(int players) => players == 3 ? new[] { 4, 5, 6 } : new[] { 5, 6, 7 };

    /// <summary>Starting plantation per seat: Indigo, Indigo, Corn (, Corn).</summary>
    public static int[] StartPlantation(int players) => players == 3
        ? new[] { (int)Good.Indigo, (int)Good.Indigo, (int)Good.Corn }
        : new[] { (int)Good.Indigo, (int)Good.Indigo, (int)Good.Corn, (int)Good.Corn };

    /// <summary>Goods supply at start, indexed by <see cref="Good"/>: corn 10, indigo 11, sugar 11, tobacco 9, coffee 9.</summary>
    public static readonly int[] GoodsSupply = { 10, 11, 11, 9, 9 };

    /// <summary>All 50 plantation tiles by good: corn 10, indigo 12, sugar 11, tobacco 9, coffee 8.</summary>
    public static readonly int[] PlantationTotal = { 10, 12, 11, 9, 8 };

    /// <summary>Plantation tiles in the draw pile after dealing the starting plantations (3 players 47, 4 players 46).</summary>
    public static int[] DeckStart(int players)
    {
        var deck = (int[])PlantationTotal.Clone();
        foreach (int g in StartPlantation(players)) deck[g]--;
        return deck;
    }

    /// <summary>Base sale price in the trading house, indexed by <see cref="Good"/>: 0/1/2/3/4.</summary>
    public static readonly int[] BasePrice = { 0, 1, 2, 3, 4 };

    /// <summary>Factory coins by number of kinds of goods produced (index 0..5).</summary>
    public static readonly int[] FactoryCoins = { 0, 0, 1, 2, 3, 5 };
}

public enum Good : byte { Corn = 0, Indigo = 1, Sugar = 2, Tobacco = 3, Coffee = 4 }

/// <summary>Prospector exists only in 4-player games.</summary>
public enum Role : byte { Settler = 0, Mayor = 1, Builder = 2, Craftsman = 3, Trader = 4, Captain = 5, Prospector = 6 }

public enum Phase : byte
{
    ChooseRole,
    Settler,
    Mayor,
    Builder,
    CraftsmanBonus,
    Trader,
    Captain,
    CaptainStorage,
    GameOver,
}

/// <summary>Bit flags describing why the game is ending (rules.md section 5).</summary>
[Flags]
public enum EndFlags : byte
{
    None = 0,
    VpExhausted = 1,
    ColonistsShort = 2,
    CityFull = 4,
    RoundLimit = 8,
    /// <summary>Safety stop: too many decisions in one game.</summary>
    DecisionLimit = 16,
}
