using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// "Wharf rush": farm first, then buy the Wharf (9 coins, quarry discount up to 3) and ship with it. The Wharf's private
/// ship takes ALL barrels of one good in a Captain phase, ignoring capacity and the public ships, so the plan is one big
/// stack (mostly corn, which needs no production building) shipped through the Wharf every time, plus whatever fits on
/// the public ships. Unlike the Harbor rush it does not need a Harbor (one is bought later only as a +1 VP bonus).
/// Before the race starts (<c>wharfReadyTiles</c> tiles or round <c>wharfReadyRound</c>) it farms with the default economy;
/// then it buys nothing but the Wharf, selling indigo/sugar for coins and taking <c>quarryTarget</c> quarries for the discount.
/// After the Wharf: warehouses (the stack survives the end of the Captain phase), then Harbor, and the Captain role whenever
/// a big stack is waiting. The Wharf shipment is always loaded first, the largest stack on it (the Wharf takes everything, ships do not).
/// Parameters (defaults from sweeps/round6: three quarries save 3 of the 9 coins; more quarries or a later start change nothing, an earlier start is worse): <c>quarryTarget</c> (default 3), <c>wharfReadyTiles</c> (default 7), <c>wharfReadyRound</c> (default 4 with 3 players / 6 with 4), <c>buildThreshold</c> (default 4).
/// </summary>
public sealed class WharfRushStrategy : HeuristicStrategy
{
    private const int Indigo = (int)Good.Indigo;
    private const int Sugar = (int)Good.Sugar;
    private const int Wharf = (int)BuildingId.Wharf;

    private int _quarryTarget;
    private int _readyTiles;
    private int _readyRound;

    public WharfRushStrategy(IReadOnlyDictionary<string, JsonElement> parameters) : base(parameters, 4.0) { }

    protected override void Configure(int players)
    {
        _quarryTarget = (int)Param("quarryTarget", players, 3, 3);
        _readyTiles = (int)Param("wharfReadyTiles", players, 7, 7);
        _readyRound = (int)Param("wharfReadyRound", players, 4, 6);
    }

    private static bool Owns(GameState s, int me, int b) => s.BuildingOwned[me * B + b] != 0;

    /// <summary>True while the Wharf is the goal: not owned, still available and the farming phase is over.</summary>
    private bool SeekingWharf(GameState s, int me) =>
        !Owns(s, me, Wharf) && s.BuildingSupply[Wharf] > 0 && (s.TileCount(me) >= _readyTiles || s.Round >= _readyRound);

    private static bool OwnsAnyProducer(GameState s, int me, int good)
    {
        foreach (int b in Buildings.ProducersOf[good])
            if (s.BuildingOwned[me * B + b] != 0) return true;
        return false;
    }

    protected override double TileValue(GameState s, int me, int good)
    {
        if (good == Corn) return 9;
        if (good <= Sugar) return SeekingWharf(s, me) ? 6 : 5;
        return 2.5;
    }

    protected override double QuarryValue(GameState s, int me) =>
        QuarriesOwned(s, me) < _quarryTarget ? (SeekingWharf(s, me) ? 9 : 6) : 3;

    protected override double BuildingWanted(GameState s, int me, int building)
    {
        if (building == Wharf) return 99;
        if (SeekingWharf(s, me)) return 0; // nothing but the Wharf while it is the goal
        if (!Owns(s, me, Wharf))
            return building switch
            {
                (int)BuildingId.Hacienda => 7.5,
                (int)BuildingId.Hospice => 7,
                (int)BuildingId.SmallIndigoPlant => 5.5,
                (int)BuildingId.SmallSugarMill => 5.5,
                _ => BaseBuildingValue[building],
            };
        return building switch
        {
            (int)BuildingId.SmallWarehouse => 8,
            (int)BuildingId.LargeWarehouse => 7,
            (int)BuildingId.Harbor => 8.5,
            (int)BuildingId.Hospice => 7,
            (int)BuildingId.Hacienda => 7,
            _ => BaseBuildingValue[building],
        };
    }

    protected override double SlotValue(GameState s, int me, int slot)
    {
        if (slot < T)
        {
            if (slot == Quarry) return SeekingWharf(s, me) && QuarriesOwned(s, me) <= _quarryTarget ? 9.5 : 5;
            if (slot == Corn) return 8;
            if (slot == Indigo || slot == Sugar) return OwnsAnyProducer(s, me, slot) ? 7 : 2;
            return base.SlotValue(s, me, slot);
        }
        int building = slot - T;
        if (building == Wharf) return 12;
        if (building == (int)BuildingId.SmallWarehouse || building == (int)BuildingId.LargeWarehouse) return 8;
        if (Buildings.All[building].IsProduction)
        {
            int good = Buildings.Produces[building];
            return good <= Sugar && s.Tiles[me * T + good] > 0 ? 7 : 0.5;
        }
        return base.SlotValue(s, me, slot);
    }

    protected override double ProductionWeight(GameState s, int me, int good) =>
        good == Corn ? 1.5 : good <= Sugar ? 1.0 : 0.6;

    protected override double SellValue(GameState s, int me, int good)
    {
        int price = Rules.SalePrice(s, me, good);
        if (good == Corn) return 0.5; // the corn stack is what the Wharf ships
        if (SeekingWharf(s, me)) return price >= 1 ? 2 + price : 0.5; // coins for the 9-coin Wharf
        return price >= 2 ? 2 + price : 0.5;
    }

    /// <summary>Keep the biggest stack over the end of the Captain phase (the Wharf ships all of it).</summary>
    protected override double KeepValue(GameState s, int me, int good, int count) => count * 3 + (good == Corn ? 1 : 0);

    protected override double TraderRoleValue(GameState s, int me)
    {
        if (!SeekingWharf(s, me)) return base.TraderRoleValue(s, me) * 0.6;
        double v = 0.3;
        for (int g = 1; g < G; g++)
            if (s.Goods[me * G + g] > 0) v += 1.0 + GameConstants.BasePrice[g];
        return v;
    }

    protected override double RoleCoinWeight(GameState s, int me) => SeekingWharf(s, me) ? 1.5 : 1.0;

    /// <summary>The Wharf shipment is always the largest stack; the rest goes on public ships. +1 VP privilege.</summary>
    protected override double WharfLoadValue(GameState s, int me, int good, int count) =>
        count * 10 + 3 + (good == Corn ? 1 : 0);

    protected override double CaptainRoleValue(GameState s, int me)
    {
        if (s.GoodTotal(me) == 0) return 0;
        if (!s.HasOccupied(me, BuildingId.Wharf)) return base.CaptainRoleValue(s, me) * 0.8;

        double bonus = s.HasOccupied(me, BuildingId.Harbor) ? 1.0 : 0.0;
        int most = 0, mostGood = -1;
        for (int g = 0; g < G; g++)
            if (s.Goods[me * G + g] > most) { most = s.Goods[me * G + g]; mostGood = g; }
        double total = most + bonus; // the whole biggest stack through the Wharf
        for (int g = 0; g < G; g++)
        {
            if (g == mostGood || s.Goods[me * G + g] == 0) continue;
            int load = Math.Min(s.Goods[me * G + g], ShipRoom(s, g));
            if (load > 0) total += load + bonus;
        }
        return 3 + 0.9 * total + 1;
    }
}
