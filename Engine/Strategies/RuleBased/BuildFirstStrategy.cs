using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// "Build first": turn every coin into buildings as fast as possible. It takes quarries (cheaper buildings), grows a
/// mixed economy (indigo, sugar, tobacco, coffee), sells goods for coins, picks Builder whenever something worth buying
/// is affordable, and aims at the large buildings whose end-of-game bonus it can actually fill
/// (Residence with a full island, City Hall with many violet buildings, Guild Hall with production buildings,
/// Fortress with many colonists, Customs House with many VP chips). It mans buildings before plantations.
/// Parameters: <c>buildThreshold</c> (default 4.5, tuned by a 4-player sweep; lower values buy too much junk).
/// </summary>
public sealed class BuildFirstStrategy : HeuristicStrategy
{
    private readonly int _quarryTarget;

    public BuildFirstStrategy(IReadOnlyDictionary<string, JsonElement> parameters) : base(parameters, 4.5)
    {
        _quarryTarget = (int)StrategyRegistry.GetDouble(parameters, "quarryTarget", 3);
    }

    private static bool Owns(GameState s, int me, BuildingId b) => s.BuildingOwned[me * B + (int)b] != 0;

    private static bool IsLarge(int building) => Buildings.All[building].Large;

    private static int VioletOwned(GameState s, int me)
    {
        int n = 0;
        for (int b = 0; b < B; b++)
            if (s.BuildingOwned[me * B + b] != 0 && Buildings.All[b].IsViolet) n++;
        return n;
    }

    private static int ProductionScore(GameState s, int me)
    {
        int n = 0;
        for (int b = 0; b < B; b++)
            if (s.BuildingOwned[me * B + b] != 0 && Buildings.All[b].IsProduction) n += Buildings.Tier[b] == 1 ? 1 : 2;
        return n;
    }

    protected override double BuildingWanted(GameState s, int me, int building)
    {
        var info = Buildings.All[building];
        switch ((BuildingId)building)
        {
            case BuildingId.Residence: return 4 + 0.9 * Math.Max(0, s.TileCount(me) - 6);
            case BuildingId.CityHall: return 3 + 0.8 * (VioletOwned(s, me) + 1);
            case BuildingId.GuildHall: return 3 + 0.7 * ProductionScore(s, me);
            case BuildingId.Fortress: return 3 + 0.35 * s.ColonistsOnBoard(me);
            case BuildingId.CustomsHouse: return 3 + 0.2 * s.VpChips[me];
        }
        double v = building switch
        {
            (int)BuildingId.SmallIndigoPlant => 4.5,
            (int)BuildingId.SmallSugarMill => 4.5,
            (int)BuildingId.SmallMarket => 4,
            (int)BuildingId.Hacienda => 4,
            (int)BuildingId.ConstructionHut => 3.5,
            (int)BuildingId.SmallWarehouse => 3.5,
            (int)BuildingId.LargeIndigoPlant => 5,
            (int)BuildingId.LargeSugarMill => 5,
            (int)BuildingId.Hospice => 4.5,
            (int)BuildingId.Office => 3.5,
            (int)BuildingId.LargeMarket => 6.5,
            (int)BuildingId.LargeWarehouse => 4.5,
            (int)BuildingId.TobaccoStorage => 6,
            (int)BuildingId.CoffeeRoaster => 6.5,
            (int)BuildingId.Factory => 5,
            (int)BuildingId.University => 5.5,
            (int)BuildingId.Harbor => 6.5,
            (int)BuildingId.Wharf => 5.5,
            _ => 3,
        };
        // A production building is only worth it if we grow that good.
        if (info.IsProduction && s.Tiles[me * T + info.Produces] == 0) v -= 2.5;
        return v;
    }

    protected override double SlotValue(GameState s, int me, int slot)
    {
        if (slot < T)
        {
            if (slot == Quarry) return 7;
            foreach (int b in Buildings.ProducersOf[slot == Corn ? 0 : slot])
                if (s.BuildingOwned[me * B + b] != 0) return 8;
            return slot == Corn ? 6 : 3;
        }
        int building = slot - T;
        var info = Buildings.All[building];
        if (info.IsProduction) return s.Tiles[me * T + info.Produces] > 0 ? 9 : 1;
        if (IsLarge(building)) return BuildingWanted(s, me, building) + 3; // its bonus only counts when manned
        if (building == (int)BuildingId.SmallMarket || building == (int)BuildingId.LargeMarket) return 6;
        return BuildingWanted(s, me, building) + 1.5;
    }

    protected override double TileValue(GameState s, int me, int good)
    {
        if (good == Corn) return 5;
        return good <= (int)Good.Sugar ? 7 : 6.5;
    }

    protected override double QuarryValue(GameState s, int me) => QuarriesOwned(s, me) < _quarryTarget ? 9 : 3;

    protected override double ProductionWeight(GameState s, int me, int good) => good switch
    {
        (int)Good.Corn => 0.8,
        (int)Good.Indigo => 1.2,
        (int)Good.Sugar => 1.5,
        (int)Good.Tobacco => 2.0,
        _ => 2.5,
    };

    protected override double BonusGoodValue(GameState s, int me, int good) =>
        ProductionWeight(s, me, good) * 3 + GameConstants.BasePrice[good];

    protected override double SellValue(GameState s, int me, int good)
    {
        int price = Rules.SalePrice(s, me, good);
        return price >= 1 ? 3 + price : 0.5; // coins buy buildings
    }

    protected override double TraderRoleValue(GameState s, int me)
    {
        double v = 0.3;
        for (int g = 0; g < G; g++)
            if (s.Goods[me * G + g] > 0) v += 0.9 * (GameConstants.BasePrice[g] + 1);
        return v;
    }

    protected override double SettlerRoleValue(GameState s, int me)
    {
        int tiles = s.TileCount(me);
        if (tiles >= GameConstants.MaxTiles) return 0;
        if (QuarriesOwned(s, me) < _quarryTarget) return 8;
        return 5.5 - (tiles >= 9 ? 2 : 0);
    }

    protected override double RoleCoinWeight(GameState s, int me) => 1.3;
}
