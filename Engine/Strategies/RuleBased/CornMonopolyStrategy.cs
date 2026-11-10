using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// "Corn monopoly": a spoiler that only wants to take part. It loves corn: every corn plantation (also the face-up ones other
/// players would want) goes to it, it hoards the corn barrels instead of shipping or selling them (corn supply is only
/// 10 barrels, so a full hoard leaves the other players without corn) and keeps them across the Captain phase with warehouses.
/// It avoids the Captain role and never sells corn; if a Captain phase leaves it no other choice it ships the other goods first.
/// It buys almost nothing except warehouses (to keep the hoard), a Hacienda and a Hospice.
/// Parameters: <c>buildThreshold</c> (default 4).
/// </summary>
public sealed class CornMonopolyStrategy : HeuristicStrategy
{
    private const int SmallWarehouse = (int)BuildingId.SmallWarehouse;
    private const int LargeWarehouse = (int)BuildingId.LargeWarehouse;

    public CornMonopolyStrategy(IReadOnlyDictionary<string, JsonElement> parameters) : base(parameters, 4.0) { }

    protected override double TileValue(GameState s, int me, int good) => good == Corn ? 20 : 1;

    protected override double QuarryValue(GameState s, int me) => 2;

    protected override double SettlerRoleValue(GameState s, int me)
    {
        if (s.TileCount(me) >= GameConstants.MaxTiles) return 0;
        return s.FaceUp[Corn] > 0 ? 12 : 3; // corn on offer: take it before anybody else does
    }

    protected override double BuildingWanted(GameState s, int me, int building) => building switch
    {
        SmallWarehouse => 9,
        LargeWarehouse => 8.5,
        (int)BuildingId.Hacienda => 8,
        (int)BuildingId.Hospice => 6,
        _ => 0,
    };

    protected override double SlotValue(GameState s, int me, int slot)
    {
        if (slot < T) return slot == Corn ? 10 : slot == Quarry ? 2 : 1;
        int building = slot - T;
        if (building == SmallWarehouse || building == LargeWarehouse) return 11;
        return Buildings.All[building].IsProduction ? 0.5 : BaseBuildingValue[building];
    }

    protected override double ProductionWeight(GameState s, int me, int good) => good == Corn ? 3 : 0.3;

    protected override double SellValue(GameState s, int me, int good) =>
        good == Corn ? 0 : 2 + GameConstants.BasePrice[good]; // never sells corn (passing scores 1)

    protected override double KeepValue(GameState s, int me, int good, int count) =>
        good == Corn ? 1000 + count : count * (GameConstants.BasePrice[good] + 1);

    protected override double TraderRoleValue(GameState s, int me) => 0.3;

    protected override double CaptainRoleValue(GameState s, int me) => 0;

    /// <summary>When it must load something, corn comes last (the penalty outweighs any number of barrels).</summary>
    protected override double ShipGoodBias(GameState s, int me, int good) => good == Corn ? -100 : 0;

    protected override double WharfLoadValue(GameState s, int me, int good, int count) =>
        count * 10 + ShipGoodBias(s, me, good) - 0.5;
}
