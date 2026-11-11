using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// "Corn monopoly": a spoiler that only wants to take part. It has two means, which the variants switch on separately
/// (to measure which one hurts the other corn players, docs/strategy-analysis.md 7.4):
/// <list type="bullet">
/// <item><b>grab</b> (<c>corn-monopoly-tiles</c>): every corn plantation goes to it (also the face-up ones other players would want),
/// Settler is chosen whenever corn is on offer; everything else plays like the corn shipper (it ships and sells normally).</item>
/// <item><b>hoard</b> (<c>corn-monopoly-hoard</c>): plantations are taken like the corn shipper, but the corn barrels are never sold and never
/// shipped voluntarily (corn supply is only 10 barrels, so a full hoard leaves the others without corn); warehouses keep the hoard
/// across the Captain phase, the Captain role is avoided and when it must load it ships the other goods first.</item>
/// </list>
/// <c>corn-monopoly</c> does both and buys almost nothing except warehouses, a Hacienda and a Hospice.
/// Parameters: <c>buildThreshold</c> (default 4).
/// </summary>
public sealed class CornMonopolyStrategy : HeuristicStrategy
{
    private const int SmallWarehouse = (int)BuildingId.SmallWarehouse;
    private const int LargeWarehouse = (int)BuildingId.LargeWarehouse;

    private readonly bool _grab;
    private readonly bool _hoard;

    public CornMonopolyStrategy(IReadOnlyDictionary<string, JsonElement> parameters, bool grab = true, bool hoard = true) : base(parameters, 4.0)
    {
        _grab = grab;
        _hoard = hoard;
    }

    protected override double TileValue(GameState s, int me, int good) =>
        _grab ? (good == Corn ? 20 : 1) : base.TileValue(s, me, good);

    protected override double QuarryValue(GameState s, int me) => _grab ? 2 : base.QuarryValue(s, me);

    protected override double SettlerRoleValue(GameState s, int me)
    {
        if (!_grab) return base.SettlerRoleValue(s, me);
        if (s.TileCount(me) >= GameConstants.MaxTiles) return 0;
        return s.FaceUp[Corn] > 0 ? 12 : 3; // corn on offer: take it before anybody else does
    }

    protected override double BuildingWanted(GameState s, int me, int building)
    {
        if (!_hoard) return base.BuildingWanted(s, me, building);
        return building switch
        {
            SmallWarehouse => 9,
            LargeWarehouse => 8.5,
            (int)BuildingId.Hacienda => 8,
            (int)BuildingId.Hospice => 6,
            _ => 0,
        };
    }

    protected override double SlotValue(GameState s, int me, int slot)
    {
        if (!_hoard) return base.SlotValue(s, me, slot);
        if (slot < T) return slot == Corn ? 10 : slot == Quarry ? 2 : 1;
        int building = slot - T;
        if (building == SmallWarehouse || building == LargeWarehouse) return 11;
        return Buildings.All[building].IsProduction ? 0.5 : BaseBuildingValue[building];
    }

    protected override double ProductionWeight(GameState s, int me, int good) =>
        _hoard ? (good == Corn ? 3 : 0.3) : base.ProductionWeight(s, me, good);

    protected override double SellValue(GameState s, int me, int good)
    {
        if (!_hoard) return base.SellValue(s, me, good);
        return good == Corn ? 0 : 2 + GameConstants.BasePrice[good]; // never sells corn (passing scores 1)
    }

    protected override double KeepValue(GameState s, int me, int good, int count)
    {
        if (!_hoard) return base.KeepValue(s, me, good, count);
        return good == Corn ? 1000 + count : count * (GameConstants.BasePrice[good] + 1);
    }

    protected override double TraderRoleValue(GameState s, int me) => _hoard ? 0.3 : base.TraderRoleValue(s, me);

    protected override double CaptainRoleValue(GameState s, int me) => _hoard ? 0 : base.CaptainRoleValue(s, me);

    /// <summary>When the hoarder must load something, corn comes last (the penalty outweighs any number of barrels).</summary>
    protected override double ShipGoodBias(GameState s, int me, int good) =>
        _hoard ? (good == Corn ? -100 : 0) : base.ShipGoodBias(s, me, good);
}
