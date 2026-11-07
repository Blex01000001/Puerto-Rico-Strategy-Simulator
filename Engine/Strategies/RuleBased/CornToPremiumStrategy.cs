using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// "Corn, then tobacco/coffee": early on it plays the corn shipper (corn needs no building and ships for VP while
/// coins are scarce). From the middle game it moves to tobacco or coffee, whichever it can get at more easily
/// (it already owns the producer building, or has plantations / sees them face up), builds that producer, mans it
/// and sells the goods to the trading house for coins. It keeps shipping corn for VP throughout.
/// Parameters: <c>switchRound</c> (default 7 for 4 players, 9 for 3) and <c>cornTarget</c> (default 4 corn plantations for 4 players, 5 for 3; tuned by sweeps, see sweeps/round2 and sweeps/3p) decide when the
/// middle game starts (whichever comes first); <c>traderWeight</c> (default 1.5) scales the Trader role value in the middle game; <c>buildThreshold</c> (default 4.0 for 4 players, where 5.0 lost about 10 points of win share, and 5.0 for 3).
/// </summary>
public sealed class CornToPremiumStrategy : HeuristicStrategy
{
    private const int Tobacco = (int)Good.Tobacco;
    private const int Coffee = (int)Good.Coffee;

    private int _switchRound;
    private int _cornTarget;
    private double _traderWeight;

    public CornToPremiumStrategy(IReadOnlyDictionary<string, JsonElement> parameters) : base(parameters, 4.0, 5.0) { }

    protected override void Configure(int players)
    {
        _switchRound = (int)Param("switchRound", players, 9, 7);
        _cornTarget = (int)Param("cornTarget", players, 5, 4);
        _traderWeight = Param("traderWeight", players, 1.5, 1.5);
    }

    private bool MidGame(GameState s, int me) => s.Round >= _switchRound || CornTiles(s, me) >= _cornTarget;

    private static bool OwnsProducer(GameState s, int me, int good)
    {
        foreach (int b in Buildings.ProducersOf[good])
            if (s.BuildingOwned[me * B + b] != 0) return true;
        return false;
    }

    /// <summary>Tobacco or coffee, whichever is easier to get: producer building owned, plantations owned, plantations face up.</summary>
    private static int Target(GameState s, int me)
    {
        double Easy(int good) =>
            (OwnsProducer(s, me, good) ? 6 : 0) + 2 * s.Tiles[me * T + good] + s.FaceUp[good] + (good == Coffee ? 0.3 : 0);
        return Easy(Coffee) >= Easy(Tobacco) ? Coffee : Tobacco;
    }

    private static bool IsPremium(int good) => good == Tobacco || good == Coffee;

    protected override double TileValue(GameState s, int me, int good)
    {
        if (!MidGame(s, me)) return base.TileValue(s, me, good);
        int target = Target(s, me);
        if (good == target) return 9;
        if (IsPremium(good)) return OwnsProducer(s, me, good) ? 7 : 4;
        if (good == Corn) return CornTiles(s, me) < 6 ? 5 : 3;
        return OwnsProducer(s, me, good) ? 3 : 1.5;
    }

    protected override double BuildingWanted(GameState s, int me, int building)
    {
        double basic = BaseBuildingValue[building];
        if (!Buildings.All[building].IsProduction || !IsPremium(Buildings.Produces[building])) return basic;
        int good = Buildings.Produces[building];
        if (!MidGame(s, me)) return 2;
        if (good == Target(s, me)) return s.Tiles[me * T + good] > 0 ? 10 : 9;
        return s.Tiles[me * T + good] > 0 ? 6 : 3;
    }

    protected override double SlotValue(GameState s, int me, int slot)
    {
        if (!MidGame(s, me)) return base.SlotValue(s, me, slot);
        int target = Target(s, me);
        if (slot < T)
        {
            if (slot == Corn) return 6;
            if (IsPremium(slot)) return OwnsProducer(s, me, slot) ? (slot == target ? 9 : 6) : 3;
            return base.SlotValue(s, me, slot);
        }
        int building = slot - T;
        if (Buildings.All[building].IsProduction && IsPremium(Buildings.Produces[building]))
        {
            int good = Buildings.Produces[building];
            if (s.Tiles[me * T + good] == 0) return 1;
            return good == target ? 9.5 : 6;
        }
        return base.SlotValue(s, me, slot);
    }

    protected override double ProductionWeight(GameState s, int me, int good)
    {
        if (!MidGame(s, me)) return base.ProductionWeight(s, me, good);
        if (good == Corn) return 1.0;
        if (good == Target(s, me)) return 2.5;
        return IsPremium(good) ? 1.8 : 0.6;
    }

    protected override double BonusGoodValue(GameState s, int me, int good) =>
        ProductionWeight(s, me, good) * 4 + GameConstants.BasePrice[good] * 0.5;

    protected override double SellValue(GameState s, int me, int good)
    {
        if (good == Corn) return 0.5;
        return (IsPremium(good) ? 4 + GameConstants.BasePrice[good] : 2 + GameConstants.BasePrice[good]);
    }

    protected override double TraderRoleValue(GameState s, int me)
    {
        if (!MidGame(s, me)) return base.TraderRoleValue(s, me);
        double v = 0.3;
        for (int g = 1; g < G; g++)
            if (s.Goods[me * G + g] > 0) v += 0.8 * (GameConstants.BasePrice[g] + 1);
        return v * _traderWeight;
    }

    protected override double KeepValue(GameState s, int me, int good, int count)
    {
        if (!MidGame(s, me)) return base.KeepValue(s, me, good, count);
        if (good == Corn) return count * 2;
        return count * (GameConstants.BasePrice[good] + 1) * (IsPremium(good) ? 1.5 : 1);
    }

    protected override double SettlerRoleValue(GameState s, int me)
    {
        if (!MidGame(s, me)) return base.SettlerRoleValue(s, me);
        int tiles = s.TileCount(me);
        if (tiles >= GameConstants.MaxTiles) return 0;
        int target = Target(s, me);
        return 4 + (s.FaceUp[target] > 0 ? 2.5 : 0) - (tiles >= 10 ? 2 : 0);
    }
}
