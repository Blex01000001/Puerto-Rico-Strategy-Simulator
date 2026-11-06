using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// "Harbor rush": do whatever it takes to own a Harbor, then use it. Every shipment earns +1 VP on top of the
/// barrels, so after the Harbor it wants many separate shipments: diverse goods (corn, indigo, sugar), the Wharf,
/// and the Captain role as often as possible.
/// Before the Harbor it spends nothing on anything else and collects coins (role coins, selling goods) and
/// Harbor discounts (manned quarries, the Builder privilege), choosing Builder the moment the Harbor is affordable.
/// Parameters: <c>quarryTarget</c> (default 0 = take no quarries; the 4-player sweep found quarries not worth a turn; the tier-3 Harbor discount would cap at 3), <c>buildThreshold</c> (default 4).
/// </summary>
public sealed class HarborRushStrategy : HeuristicStrategy
{
    private const int Indigo = (int)Good.Indigo;
    private const int Sugar = (int)Good.Sugar;
    private const int Harbor = (int)BuildingId.Harbor;

    private readonly int _quarryTarget;

    public HarborRushStrategy(IReadOnlyDictionary<string, JsonElement> parameters) : base(parameters, 4.0)
    {
        _quarryTarget = (int)StrategyRegistry.GetDouble(parameters, "quarryTarget", 0);
    }

    /// <summary>True while the Harbor is still the goal: not owned and still available.</summary>
    private static bool SeekingHarbor(GameState s, int me) =>
        s.BuildingOwned[me * B + Harbor] == 0 && s.BuildingSupply[Harbor] > 0;

    protected override double TileValue(GameState s, int me, int good)
    {
        if (good == Corn) return 8;
        if (SeekingHarbor(s, me)) return good <= Sugar ? 4.5 : 2;
        if (good == Indigo) return 7;
        if (good == Sugar) return OwnsAnyProducer(s, me, Sugar) ? 7 : 6;
        return 3;
    }

    private static bool OwnsAnyProducer(GameState s, int me, int good)
    {
        foreach (int b in Buildings.ProducersOf[good])
            if (s.BuildingOwned[me * B + b] != 0) return true;
        return false;
    }

    protected override double QuarryValue(GameState s, int me)
    {
        if (SeekingHarbor(s, me) && QuarriesOwned(s, me) < _quarryTarget) return 9;
        return 3;
    }

    protected override double BuildingWanted(GameState s, int me, int building)
    {
        if (building == Harbor) return 99;
        if (SeekingHarbor(s, me)) return 0; // nothing but the Harbor until we own it
        return building switch
        {
            (int)BuildingId.Wharf => 9.5,
            (int)BuildingId.SmallWarehouse => 7,
            (int)BuildingId.Hospice => 7,
            (int)BuildingId.Hacienda => 7.5,
            (int)BuildingId.SmallIndigoPlant => 5.5,
            (int)BuildingId.SmallSugarMill => 5.5,
            _ => BaseBuildingValue[building],
        };
    }

    protected override double SlotValue(GameState s, int me, int slot)
    {
        if (slot < T)
        {
            if (slot == Quarry) return SeekingHarbor(s, me) ? 9.5 : 5;
            if (slot == Corn) return 8;
            if (slot == Indigo || slot == Sugar) return OwnsAnyProducer(s, me, slot) ? 7 : 2;
            return base.SlotValue(s, me, slot);
        }
        int building = slot - T;
        if (building == Harbor) return 12;
        if (building == (int)BuildingId.Wharf) return 11;
        if (Buildings.All[building].IsProduction)
        {
            int good = Buildings.Produces[building];
            return good <= Sugar && s.Tiles[me * T + good] > 0 ? 7 : 0.5;
        }
        return base.SlotValue(s, me, slot);
    }

    protected override double ProductionWeight(GameState s, int me, int good) =>
        good == Corn ? 1.5 : good <= Sugar ? 1.3 : 0.7;

    protected override double BonusGoodValue(GameState s, int me, int good)
    {
        // a new kind of good = a new shipment; prefer the kind we hold least of
        return 10 - s.Goods[me * G + good] + (good <= Sugar ? 1 : 0);
    }

    protected override double SellValue(GameState s, int me, int good)
    {
        int price = Rules.SalePrice(s, me, good);
        if (SeekingHarbor(s, me)) return price >= 1 ? 2 + price : 0.5; // coins for the Harbor
        return price >= 3 ? 2 + price : 0.5;                           // otherwise keep goods for shipments
    }

    protected override double TraderRoleValue(GameState s, int me)
    {
        if (!SeekingHarbor(s, me)) return base.TraderRoleValue(s, me) * 0.5;
        double v = 0.3;
        for (int g = 0; g < G; g++)
            if (s.Goods[me * G + g] > 0) v += 1.0 + GameConstants.BasePrice[g];
        return v;
    }

    protected override double SettlerRoleValue(GameState s, int me)
    {
        int tiles = s.TileCount(me);
        if (tiles >= GameConstants.MaxTiles) return 0;
        if (SeekingHarbor(s, me) && QuarriesOwned(s, me) < _quarryTarget) return 9;
        return 5 + (tiles < 8 ? 1.5 : 0) - (tiles >= 10 ? 2 : 0);
    }

    protected override double RoleCoinWeight(GameState s, int me) => SeekingHarbor(s, me) ? 1.6 : 1.0;

    /// <summary>
    /// After the Harbor: count the shipments (each = barrels + 1 Harbor VP) the held goods could make this phase,
    /// one per distinct good while ships last, plus one Wharf shipment.
    /// </summary>
    protected override double CaptainRoleValue(GameState s, int me)
    {
        if (s.GoodTotal(me) == 0) return 0;
        bool harbor = s.HasOccupied(me, BuildingId.Harbor);
        double bonus = harbor ? 1.0 : 0.0;

        Span<int> counts = stackalloc int[G];
        for (int g = 0; g < G; g++) counts[g] = s.Goods[me * G + g];
        Span<bool> shipUsed = stackalloc bool[GameConstants.ShipCount];
        double total = 0;
        int shipments = 0;
        for (int round = 0; round < GameConstants.ShipCount; round++)
        {
            int bestGood = -1;
            double bestGain = 0;
            for (int g = 0; g < G; g++)
            {
                if (counts[g] == 0) continue;
                int room = ShipRoomExcluding(s, g, shipUsed);
                if (room == 0) continue;
                double gain = Math.Min(counts[g], room) + bonus;
                if (gain > bestGain) { bestGain = gain; bestGood = g; }
            }
            if (bestGood < 0) break;
            total += bestGain;
            shipments++;
            counts[bestGood] = 0;
            MarkShip(s, bestGood, shipUsed);
        }
        if (s.HasOccupied(me, BuildingId.Wharf))
        {
            int most = 0;
            for (int g = 0; g < G; g++) most = Math.Max(most, counts[g]);
            if (most > 0) { total += most + bonus; shipments++; }
        }
        if (shipments == 0) return 0;
        return (harbor ? 3 : 1.5) + 0.9 * total + 1;
    }

    private static int ShipRoomExcluding(GameState s, int good, Span<bool> used)
    {
        for (int i = 0; i < GameConstants.ShipCount; i++)
            if (s.ShipLoad[i] > 0 && s.ShipGood[i] == good)
                return used[i] ? 0 : s.ShipCap[i] - s.ShipLoad[i];
        int room = 0;
        for (int i = 0; i < GameConstants.ShipCount; i++)
            if (s.ShipLoad[i] == 0 && !used[i]) room = Math.Max(room, s.ShipCap[i]);
        return room;
    }

    private static void MarkShip(GameState s, int good, Span<bool> used)
    {
        for (int i = 0; i < GameConstants.ShipCount; i++)
            if (s.ShipLoad[i] > 0 && s.ShipGood[i] == good) { used[i] = true; return; }
        int best = -1;
        for (int i = 0; i < GameConstants.ShipCount; i++)
            if (s.ShipLoad[i] == 0 && !used[i] && (best < 0 || s.ShipCap[i] > s.ShipCap[best])) best = i;
        if (best >= 0) used[best] = true;
    }
}
