using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// "Cheap engine": copied from what MCTS plays (analysis in docs/strategy-analysis.md section 5). It buys the cheap 1-VP
/// buildings very early (Small Indigo Plant, Small Market, Small Sugar Mill, Hospice), keeps a small balanced set of
/// corn / indigo / sugar plantations instead of a big one, never pays for a Hacienda, and ships often (many small shipments)
/// rather than waiting for big loads.
/// Parameters: <c>buildThreshold</c> (default 2.0: cheap buildings clear it), <c>tileCap</c> (default 4: stop choosing Settler once it owns that many tiles;
/// 4-player sweeps: 8 gave 15%, 4 gave 29%), <c>smallValue</c> (default 8: value of the cheap early buildings; 8 or more behave the same).
/// </summary>
public sealed class CheapEngineStrategy : HeuristicStrategy
{
    private const int Indigo = (int)Good.Indigo;
    private const int Sugar = (int)Good.Sugar;

    private int _tileCap;
    private double _smallValue;

    public CheapEngineStrategy(IReadOnlyDictionary<string, JsonElement> parameters) : base(parameters, 2.0) { }

    protected override void Configure(int players)
    {
        _tileCap = (int)Param("tileCap", players, 4, 4);
        _smallValue = Param("smallValue", players, 8, 8);
    }

    private static bool Owns(GameState s, int me, int b) => s.BuildingOwned[me * B + b] != 0;

    protected override double TileValue(GameState s, int me, int good)
    {
        if (good > Sugar) return 2.5;
        // balance corn / indigo / sugar: prefer the one we hold least of
        double have = s.Tiles[me * T + good];
        return 7 - have * 0.8 + (good == Indigo ? 0.3 : 0);
    }

    protected override double QuarryValue(GameState s, int me) => QuarriesOwned(s, me) >= 1 ? 2 : 4;

    protected override double BuildingWanted(GameState s, int me, int building)
    {
        switch ((BuildingId)building)
        {
            case BuildingId.SmallIndigoPlant:
            case BuildingId.SmallSugarMill:
            case BuildingId.SmallMarket:
                return _smallValue;
            case BuildingId.Hospice: return 7;
            case BuildingId.LargeIndigoPlant: return Owns(s, me, (int)BuildingId.SmallIndigoPlant) || s.Tiles[me * T + Indigo] >= 2 ? 7.5 : 5;
            case BuildingId.LargeSugarMill: return Owns(s, me, (int)BuildingId.SmallSugarMill) || s.Tiles[me * T + Sugar] >= 2 ? 7 : 4.5;
            case BuildingId.Hacienda: return 3;
            default: return BaseBuildingValue[building];
        }
    }

    protected override double SlotValue(GameState s, int me, int slot)
    {
        if (slot < T)
        {
            if (slot == Quarry) return 3;
            if (slot <= Sugar) return 8;
            return 2;
        }
        int building = slot - T;
        if (building == (int)BuildingId.SmallMarket) return 5;
        if (Buildings.All[building].IsProduction)
            return s.Tiles[me * T + Buildings.Produces[building]] > 0 ? 7 : 0.5;
        return base.SlotValue(s, me, slot);
    }

    protected override double ProductionWeight(GameState s, int me, int good) => good <= Sugar ? 1.2 : 0.4;

    protected override double BonusGoodValue(GameState s, int me, int good) =>
        good <= Sugar ? 6 - s.Goods[me * G + good] * 0.5 + good * 0.3 : 1;

    protected override double SettlerRoleValue(GameState s, int me)
    {
        int tiles = s.TileCount(me);
        return tiles >= _tileCap ? 0.5 : 6 - tiles * 0.2;
    }

    /// <summary>Ship whenever anything can be shipped: value grows with the barrels that fit on ships.</summary>
    protected override double CaptainRoleValue(GameState s, int me)
    {
        double gain = 0;
        for (int g = 0; g < G; g++)
        {
            int have = s.Goods[me * G + g];
            if (have == 0) continue;
            gain += Math.Min(have, ShipRoom(s, g));
        }
        if (s.HasOccupied(me, BuildingId.Wharf)) gain += 1;
        return gain == 0 ? 0 : 2.5 + 1.2 * gain + (s.HasOccupied(me, BuildingId.Harbor) ? 2 : 0);
    }

    protected override double TraderRoleValue(GameState s, int me)
    {
        double v = 0.3;
        for (int g = 1; g < G; g++)
            if (s.Goods[me * G + g] > 0) v += 0.9 + 0.5 * GameConstants.BasePrice[g] + (Owns(s, me, (int)BuildingId.SmallMarket) ? 0.8 : 0);
        return v;
    }
}
