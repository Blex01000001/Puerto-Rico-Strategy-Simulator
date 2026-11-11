using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// "Wharf premium": the Wharf rush financed by an expensive good. Corn sells for nothing, so the plain Wharf rush waits
/// until round 9-10 for its 9 coins; this variant first sets up tobacco or coffee (whichever is easier to get: plantation +
/// Tobacco Storage / Coffee Roaster), sells that good at the trading house (3-4 coins a barrel) until the Wharf is paid,
/// and then ships its largest stack through the Wharf every Captain phase.
/// Stages: (1) no producer of the target good yet: take target plantations (and corn), buy the producer first;
/// (2) producer owned, no Wharf: buy nothing but the Wharf, sell the premium good, Trader weighted by <c>traderWeight</c>,
/// up to <c>quarryTarget</c> quarries; (3) Wharf owned: warehouses, Harbor; premium barrels are still sold when
/// <c>sellAfterWharf</c> is 1 and the price is at least 3, otherwise everything is kept for shipping.
/// Parameters (sweeps/round7: all nearly flat, the weakness is structural): <c>quarryTarget</c> (default 1), <c>traderWeight</c> (default 2.5), <c>sellAfterWharf</c> (default 1), <c>cornTile</c> (default 7; 5 is worse), <c>buildThreshold</c> (default 4).
/// </summary>
public sealed class WharfPremiumStrategy : HeuristicStrategy
{
    private const int Tobacco = (int)Good.Tobacco;
    private const int Coffee = (int)Good.Coffee;
    private const int Wharf = (int)BuildingId.Wharf;

    private int _quarryTarget;
    private double _traderWeight;
    private bool _sellAfterWharf;
    private double _cornTile;

    public WharfPremiumStrategy(IReadOnlyDictionary<string, JsonElement> parameters) : base(parameters, 4.0) { }

    protected override void Configure(int players)
    {
        _quarryTarget = (int)Param("quarryTarget", players, 1, 1);
        _traderWeight = Param("traderWeight", players, 2.5, 2.5);
        _sellAfterWharf = Param("sellAfterWharf", players, 1, 1) >= 0.5;
        _cornTile = Param("cornTile", players, 7, 7);
    }

    private static bool Owns(GameState s, int me, int b) => s.BuildingOwned[me * B + b] != 0;
    private static bool IsPremium(int good) => good == Tobacco || good == Coffee;

    private static bool OwnsProducer(GameState s, int me, int good)
    {
        foreach (int b in Buildings.ProducersOf[good])
            if (s.BuildingOwned[me * B + b] != 0) return true;
        return false;
    }

    /// <summary>Tobacco or coffee, whichever is easier to get: producer owned, plantations owned, plantations face up.</summary>
    private static int Target(GameState s, int me)
    {
        double Easy(int good) =>
            (OwnsProducer(s, me, good) ? 6 : 0) + 2 * s.Tiles[me * T + good] + s.FaceUp[good] + (good == Coffee ? 0.3 : 0);
        return Easy(Coffee) >= Easy(Tobacco) ? Coffee : Tobacco;
    }

    private static bool HasEngine(GameState s, int me) => OwnsProducer(s, me, Tobacco) || OwnsProducer(s, me, Coffee);

    /// <summary>Stage 2: the money engine exists and the Wharf is still to be bought.</summary>
    private static bool SeekingWharf(GameState s, int me) =>
        !Owns(s, me, Wharf) && s.BuildingSupply[Wharf] > 0 && HasEngine(s, me);

    protected override double TileValue(GameState s, int me, int good)
    {
        int target = Target(s, me);
        if (good == target) return s.Tiles[me * T + good] >= 3 ? 6 : 9.5;
        if (good == Corn) return _cornTile;
        if (IsPremium(good)) return OwnsProducer(s, me, good) ? 6 : 3;
        return 2;
    }

    protected override double QuarryValue(GameState s, int me) =>
        QuarriesOwned(s, me) < _quarryTarget ? (SeekingWharf(s, me) ? 8.5 : 6) : 3;

    protected override double BuildingWanted(GameState s, int me, int building)
    {
        if (building == Wharf) return HasEngine(s, me) ? 99 : 9;
        if (SeekingWharf(s, me)) return 0; // nothing but the Wharf once the money engine runs
        if (Buildings.All[building].IsProduction)
        {
            int good = Buildings.Produces[building];
            if (!IsPremium(good)) return 1;
            if (HasEngine(s, me)) return OwnsProducer(s, me, good) ? 0 : 3;
            return good == Target(s, me) && s.Tiles[me * T + good] > 0 ? 12 : good == Target(s, me) ? 8 : 4;
        }
        if (!Owns(s, me, Wharf))
            return building switch
            {
                (int)BuildingId.Hospice => 6,
                (int)BuildingId.Hacienda => 6,
                (int)BuildingId.SmallMarket => 5,
                _ => Math.Min(BaseBuildingValue[building], 3.5), // save the coins for the producer
            };
        return building switch
        {
            (int)BuildingId.SmallWarehouse => 8,
            (int)BuildingId.LargeWarehouse => 7,
            (int)BuildingId.Harbor => 8.5,
            _ => BaseBuildingValue[building],
        };
    }

    protected override double SlotValue(GameState s, int me, int slot)
    {
        if (slot < T)
        {
            if (slot == Quarry) return SeekingWharf(s, me) ? 9 : 5;
            if (slot == Corn) return 7;
            if (IsPremium(slot)) return OwnsProducer(s, me, slot) ? 9.5 : 3;
            return 1.5;
        }
        int building = slot - T;
        if (building == Wharf) return 12;
        if (Buildings.All[building].IsProduction)
        {
            int good = Buildings.Produces[building];
            return IsPremium(good) && s.Tiles[me * T + good] > 0 ? 10 : 0.5;
        }
        if (building == (int)BuildingId.SmallWarehouse || building == (int)BuildingId.LargeWarehouse) return 8;
        return base.SlotValue(s, me, slot);
    }

    protected override double ProductionWeight(GameState s, int me, int good) =>
        IsPremium(good) ? 2.5 : good == Corn ? 1.2 : 0.5;

    protected override double BonusGoodValue(GameState s, int me, int good) =>
        ProductionWeight(s, me, good) * 4 + GameConstants.BasePrice[good] * 0.5;

    protected override double SellValue(GameState s, int me, int good)
    {
        if (good == Corn) return 0.5;
        int price = Rules.SalePrice(s, me, good);
        if (!Owns(s, me, Wharf)) return 3 + price;                 // coins for the producer and the Wharf
        return _sellAfterWharf && price >= 3 ? 2 + price : 0.5;    // afterwards the barrels are points on the private ship
    }

    protected override double TraderRoleValue(GameState s, int me)
    {
        if (Owns(s, me, Wharf) && !_sellAfterWharf) return 0.3;
        double v = 0.3;
        for (int g = 1; g < G; g++)
            if (s.Goods[me * G + g] > 0) v += 0.8 * (GameConstants.BasePrice[g] + 1);
        return v * (Owns(s, me, Wharf) ? 0.6 : _traderWeight);
    }

    protected override double RoleCoinWeight(GameState s, int me) => Owns(s, me, Wharf) ? 1.0 : 1.5;

    /// <summary>Before the Wharf keep what sells best; afterwards keep the biggest stack (the Wharf ships all of it).</summary>
    protected override double KeepValue(GameState s, int me, int good, int count) =>
        Owns(s, me, Wharf) ? count * 3 + GameConstants.BasePrice[good] * 0.1 : count * (GameConstants.BasePrice[good] + 1);

    protected override double SettlerRoleValue(GameState s, int me)
    {
        int tiles = s.TileCount(me);
        if (tiles >= GameConstants.MaxTiles) return 0;
        int target = Target(s, me);
        return 4 + (s.FaceUp[target] > 0 && s.Tiles[me * T + target] < 3 ? 3 : 0) + (tiles < 6 ? 1 : 0) - (tiles >= 10 ? 2 : 0);
    }

    /// <summary>The Wharf shipment is always the largest stack; the rest goes on public ships.</summary>
    protected override double WharfLoadValue(GameState s, int me, int good, int count) => count * 10 + 3;

    protected override double CaptainRoleValue(GameState s, int me)
    {
        if (s.GoodTotal(me) == 0) return 0;
        if (!s.HasOccupied(me, BuildingId.Wharf))
        {
            // before the Wharf the premium barrels are worth more as coins: only corn counts as cargo
            int corn = Math.Min(s.Goods[me * G + Corn], ShipRoom(s, Corn));
            return corn == 0 ? 0.5 : 2 + corn * 1.2;
        }
        double bonus = s.HasOccupied(me, BuildingId.Harbor) ? 1.0 : 0.0;
        int most = 0, mostGood = -1;
        for (int g = 0; g < G; g++)
            if (s.Goods[me * G + g] > most) { most = s.Goods[me * G + g]; mostGood = g; }
        double total = most + bonus;
        for (int g = 0; g < G; g++)
        {
            if (g == mostGood || s.Goods[me * G + g] == 0) continue;
            int load = Math.Min(s.Goods[me * G + g], ShipRoom(s, g));
            if (load > 0) total += load + bonus;
        }
        return 3 + 0.9 * total + 1;
    }
}
