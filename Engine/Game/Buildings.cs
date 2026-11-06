namespace PuertoRico.Engine.Game;

public enum BuildingId : byte
{
    SmallIndigoPlant = 0,
    SmallSugarMill,
    SmallMarket,
    Hacienda,
    ConstructionHut,
    SmallWarehouse,
    LargeIndigoPlant,
    LargeSugarMill,
    Hospice,
    Office,
    LargeMarket,
    LargeWarehouse,
    TobaccoStorage,
    CoffeeRoaster,
    Factory,
    University,
    Harbor,
    Wharf,
    GuildHall,
    Residence,
    Fortress,
    CustomsHouse,
    CityHall,
}

/// <summary>
/// Static building data (rules.md section 3). <see cref="Tier"/> is the quarry-discount cap (1..3, large = 4).
/// <see cref="Capacity"/> is the number of colonist circles. <see cref="Produces"/> is -1 for violet buildings.
/// </summary>
public sealed record BuildingInfo(
    BuildingId Id, string Name, int Cost, int Vp, int Spaces, int Tier, int Count, int Capacity, int Produces, bool Large)
{
    public bool IsProduction => Produces >= 0;
    public bool IsViolet => Produces < 0;
}

public static class Buildings
{
    public static readonly BuildingInfo[] All =
    {
        new(BuildingId.SmallIndigoPlant, "Small Indigo Plant", 1, 1, 1, 1, 4, 1, (int)Good.Indigo, false),
        new(BuildingId.SmallSugarMill, "Small Sugar Mill", 2, 1, 1, 1, 4, 1, (int)Good.Sugar, false),
        new(BuildingId.SmallMarket, "Small Market", 1, 1, 1, 1, 2, 1, -1, false),
        new(BuildingId.Hacienda, "Hacienda", 2, 1, 1, 1, 2, 1, -1, false),
        new(BuildingId.ConstructionHut, "Construction Hut", 2, 1, 1, 1, 2, 1, -1, false),
        new(BuildingId.SmallWarehouse, "Small Warehouse", 3, 1, 1, 1, 2, 1, -1, false),
        new(BuildingId.LargeIndigoPlant, "Large Indigo Plant", 3, 2, 1, 2, 3, 3, (int)Good.Indigo, false),
        new(BuildingId.LargeSugarMill, "Large Sugar Mill", 4, 2, 1, 2, 3, 3, (int)Good.Sugar, false),
        new(BuildingId.Hospice, "Hospice", 4, 2, 1, 2, 2, 1, -1, false),
        new(BuildingId.Office, "Office", 5, 2, 1, 2, 2, 1, -1, false),
        new(BuildingId.LargeMarket, "Large Market", 5, 2, 1, 2, 2, 1, -1, false),
        new(BuildingId.LargeWarehouse, "Large Warehouse", 6, 2, 1, 2, 2, 1, -1, false),
        new(BuildingId.TobaccoStorage, "Tobacco Storage", 5, 3, 1, 3, 3, 3, (int)Good.Tobacco, false),
        new(BuildingId.CoffeeRoaster, "Coffee Roaster", 6, 3, 1, 3, 3, 2, (int)Good.Coffee, false),
        new(BuildingId.Factory, "Factory", 7, 3, 1, 3, 2, 1, -1, false),
        new(BuildingId.University, "University", 8, 3, 1, 3, 2, 1, -1, false),
        new(BuildingId.Harbor, "Harbor", 8, 3, 1, 3, 2, 1, -1, false),
        new(BuildingId.Wharf, "Wharf", 9, 3, 1, 3, 2, 1, -1, false),
        new(BuildingId.GuildHall, "Guild Hall", 10, 4, 2, 4, 1, 1, -1, true),
        new(BuildingId.Residence, "Residence", 10, 4, 2, 4, 1, 1, -1, true),
        new(BuildingId.Fortress, "Fortress", 10, 4, 2, 4, 1, 1, -1, true),
        new(BuildingId.CustomsHouse, "Customs House", 10, 4, 2, 4, 1, 1, -1, true),
        new(BuildingId.CityHall, "City Hall", 10, 4, 2, 4, 1, 1, -1, true),
    };

    // Flat lookup tables for the hot paths.
    public static readonly int[] Cost = All.Select(b => b.Cost).ToArray();
    public static readonly int[] Vp = All.Select(b => b.Vp).ToArray();
    public static readonly int[] Spaces = All.Select(b => b.Spaces).ToArray();
    public static readonly int[] Tier = All.Select(b => b.Tier).ToArray();
    public static readonly int[] Count = All.Select(b => b.Count).ToArray();
    public static readonly int[] Capacity = All.Select(b => b.Capacity).ToArray();
    public static readonly int[] Produces = All.Select(b => b.Produces).ToArray();

    /// <summary>Production building ids for each good (corn has none).</summary>
    public static readonly int[][] ProducersOf =
    {
        Array.Empty<int>(),
        new[] { (int)BuildingId.SmallIndigoPlant, (int)BuildingId.LargeIndigoPlant },
        new[] { (int)BuildingId.SmallSugarMill, (int)BuildingId.LargeSugarMill },
        new[] { (int)BuildingId.TobaccoStorage },
        new[] { (int)BuildingId.CoffeeRoaster },
    };

    public static BuildingInfo Info(int id) => All[id];
}
