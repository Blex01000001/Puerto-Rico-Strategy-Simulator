namespace PuertoRico.Engine.Game;

/// <summary>Fixed numbers for the 3-player base game (rules.md section 1). Single place for setup numbers.</summary>
public static class GameConstants
{
    public const int Players = 3;
    public const int GoodCount = 5;
    /// <summary>Tile types: 0..4 = plantation of that good, 5 = quarry.</summary>
    public const int TileTypes = 6;
    public const int QuarryType = 5;
    public const int RoleCount = 6;
    public const int BuildingCount = 23;
    public const int ShipCount = 3;
    public const int TradeSlots = 4;
    public const int MaxTiles = 12;
    public const int CitySpaces = 12;
    public const int FaceUpTiles = Players + 1;
    public const int StartCoins = 2;
    public const int TotalColonists = 58;
    public const int StartShipColonists = 3;
    public const int BankColonists = 55;
    public const int VpChips = 75;
    public const int QuarryTotal = 8;
    public const int DefaultMaxRounds = 150;

    /// <summary>Public ship capacities.</summary>
    public static readonly int[] ShipCapacity = { 4, 5, 6 };

    /// <summary>Goods supply at start, indexed by <see cref="Good"/>: corn 10, indigo 11, sugar 11, tobacco 9, coffee 9.</summary>
    public static readonly int[] GoodsSupply = { 10, 11, 11, 9, 9 };

    /// <summary>Plantation tiles in the draw pile after dealing starting plantations (47 total).</summary>
    public static readonly int[] DeckStart = { 9, 10, 11, 9, 8 };

    /// <summary>Starting plantation per seat: Indigo, Indigo, Corn.</summary>
    public static readonly int[] StartPlantation = { (int)Good.Indigo, (int)Good.Indigo, (int)Good.Corn };

    /// <summary>Base sale price in the trading house, indexed by <see cref="Good"/>: 0/1/2/3/4.</summary>
    public static readonly int[] BasePrice = { 0, 1, 2, 3, 4 };

    /// <summary>Factory coins by number of kinds of goods produced (index 0..5).</summary>
    public static readonly int[] FactoryCoins = { 0, 0, 1, 2, 3, 5 };
}

public enum Good : byte { Corn = 0, Indigo = 1, Sugar = 2, Tobacco = 3, Coffee = 4 }

public enum Role : byte { Settler = 0, Mayor = 1, Builder = 2, Craftsman = 3, Trader = 4, Captain = 5 }

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
