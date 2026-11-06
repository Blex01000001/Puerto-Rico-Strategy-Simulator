using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// Hand-written "corn shipper" strategy: grow many corn plantations (they need no building), keep them manned,
/// ship corn for VP every Captain phase, and spend coins only on a short list of useful buildings
/// (Hacienda, Harbor, Wharf, Hospice, warehouses ...). Every choice is a score; the highest score wins and ties go to
/// the first legal action, so the strategy is deterministic. It only reads public information (never opponents' VP).
/// Parameters (config <c>params</c>): <c>buildThreshold</c> (default 5.0) = minimum building value worth buying.
/// </summary>
public sealed class CornShipperStrategy : IStrategy
{
    private const int T = GameConstants.TileTypes;
    private const int B = GameConstants.BuildingCount;
    private const int G = GameConstants.GoodCount;
    private const int Corn = (int)Good.Corn;

    /// <summary>How much a building is worth to this strategy (used both to buy it and to man it).</summary>
    private static readonly double[] BuildingValue = BuildValues();

    private static double[] BuildValues()
    {
        var v = new double[B];
        v[(int)BuildingId.SmallIndigoPlant] = 1; v[(int)BuildingId.SmallSugarMill] = 1;
        v[(int)BuildingId.SmallMarket] = 2; v[(int)BuildingId.Hacienda] = 8;
        v[(int)BuildingId.ConstructionHut] = 5; v[(int)BuildingId.SmallWarehouse] = 5.5;
        v[(int)BuildingId.LargeIndigoPlant] = 1; v[(int)BuildingId.LargeSugarMill] = 1;
        v[(int)BuildingId.Hospice] = 7; v[(int)BuildingId.Office] = 1;
        v[(int)BuildingId.LargeMarket] = 3; v[(int)BuildingId.LargeWarehouse] = 5;
        v[(int)BuildingId.TobaccoStorage] = 1.5; v[(int)BuildingId.CoffeeRoaster] = 1.5;
        v[(int)BuildingId.Factory] = 2; v[(int)BuildingId.University] = 5.5;
        v[(int)BuildingId.Harbor] = 9; v[(int)BuildingId.Wharf] = 8.5;
        v[(int)BuildingId.GuildHall] = 2; v[(int)BuildingId.Residence] = 7;
        v[(int)BuildingId.Fortress] = 5; v[(int)BuildingId.CustomsHouse] = 5;
        v[(int)BuildingId.CityHall] = 5;
        return v;
    }

    private readonly double _buildThreshold;

    public CornShipperStrategy(IReadOnlyDictionary<string, JsonElement> parameters)
    {
        _buildThreshold = StrategyRegistry.GetDouble(parameters, "buildThreshold", 5.0);
    }

    public GameAction ChooseAction(GameState s, IReadOnlyList<GameAction> legalActions)
    {
        if (legalActions.Count == 1) return legalActions[0];
        if (s.Phase == Phase.Mayor) return ChooseMayorPlacement(s);

        int me = s.Actor;
        int best = 0;
        double bestScore = double.NegativeInfinity;
        for (int i = 0; i < legalActions.Count; i++)
        {
            double score = Score(s, me, legalActions[i]);
            if (score > bestScore) { bestScore = score; best = i; }
        }
        return legalActions[best];
    }

    private double Score(GameState s, int me, GameAction a)
    {
        switch (a.Type)
        {
            case ActionType.ChooseRole: return RoleValue(s, me, (Role)a.A);
            case ActionType.TakePlantation:
                if (a.A == Corn) return 10;
                return 2 + 0.1 * a.A + (CornTiles(s, me) >= 8 ? 3 : 0);
            case ActionType.TakeQuarry: return QuarriesOwned(s, me) >= 3 ? 3 : 6.5;
            case ActionType.UseHacienda: return 20;
            case ActionType.Pass:
                return s.Phase switch
                {
                    Phase.Builder => _buildThreshold,
                    Phase.Settler => 0.5,
                    _ => 1.0,
                };
            case ActionType.Build: return BuildingValue[a.A] - 0.01 * Buildings.Cost[a.A];
            case ActionType.CraftsmanBonus: return a.A == Corn ? 10 : 1 + a.A;
            case ActionType.Sell: return a.A == Corn ? 0.5 : 2 + GameConstants.BasePrice[a.A];
            case ActionType.LoadShip:
                {
                    int room = GameConstants.ShipCapacity[a.B] - s.ShipLoad[a.B];
                    int vp = Math.Min(s.Goods[me * G + a.A], room);
                    return vp * 10 + (a.A == Corn ? 1 : 0) - GameConstants.ShipCapacity[a.B] * 0.01;
                }
            case ActionType.LoadWharf:
                return s.Goods[me * G + a.A] * 10 + (a.A == Corn ? 1 : 0) - 0.5;
            case ActionType.KeepGoods: return a.A == Corn ? 100 : s.Goods[me * G + a.A] * (GameConstants.BasePrice[a.A] + 1);
            case ActionType.KeepBarrel: return a.A == Corn ? 100 : GameConstants.BasePrice[a.A] + 1;
            default: return 0;
        }
    }

    // ---------------------------------------------------------------- role choice

    private double RoleValue(GameState s, int me, Role role)
    {
        double v;
        switch (role)
        {
            case Role.Captain: v = CaptainValue(s, me); break;
            case Role.Craftsman: v = CraftsmanValue(s, me); break;
            case Role.Settler:
                {
                    int tiles = s.TileCount(me);
                    v = tiles >= GameConstants.MaxTiles ? 0 : 5 + (CornTiles(s, me) < 6 ? 2 : 0) - (tiles >= 9 ? 2 : 0);
                    break;
                }
            case Role.Mayor:
                {
                    int gain = Math.Min(EmptyCircles(s, me), s.SanJuan[me] + 1 + s.ShipColonists / GameConstants.Players);
                    v = 1 + 1.6 * gain;
                    break;
                }
            case Role.Builder:
                {
                    double bestValue = 0;
                    for (int b = 0; b < B; b++)
                    {
                        if (s.BuildingOwned[me * B + b] != 0 || s.BuildingSupply[b] <= 0) continue;
                        int cost = Math.Max(0, Buildings.Cost[b] - Math.Min(s.TilesOcc[me * T + GameConstants.QuarryType], Buildings.Tier[b]) - 1);
                        if (cost > s.Coins[me] || Buildings.Spaces[b] > GameConstants.CitySpaces - s.CitySpacesUsed(me)) continue;
                        if (BuildingValue[b] > bestValue) bestValue = BuildingValue[b];
                    }
                    v = bestValue >= _buildThreshold ? bestValue - 1 : 0.5;
                    break;
                }
            default: // Trader
                {
                    int others = 0;
                    for (int g = 1; g < G; g++) others += s.Goods[me * G + g];
                    v = others > 0 ? 2.5 : 0.3;
                    break;
                }
        }
        return v + s.RoleCoins[(int)role];
    }

    private static double CaptainValue(GameState s, int me)
    {
        int corn = s.Goods[me * G + Corn];
        int total = s.GoodTotal(me);
        if (total == 0) return 0;
        int room = 0;
        int holding = -1;
        for (int i = 0; i < GameConstants.ShipCount; i++)
            if (s.ShipLoad[i] > 0 && s.ShipGood[i] == Corn) holding = i;
        if (holding >= 0) room = GameConstants.ShipCapacity[holding] - s.ShipLoad[holding];
        else
            for (int i = 0; i < GameConstants.ShipCount; i++)
                if (s.ShipLoad[i] == 0) room = Math.Max(room, GameConstants.ShipCapacity[i]);
        int loadable = Math.Min(corn, room);
        if (s.HasOccupied(me, BuildingId.Wharf)) loadable = Math.Max(loadable, corn);
        if (loadable == 0) loadable = Math.Min(total - corn, 2); // other goods can still be shipped
        if (loadable == 0) return 0;
        return 3 + loadable * 1.2 + 1 + (s.HasOccupied(me, BuildingId.Harbor) ? 2 : 0);
    }

    private static double CraftsmanValue(GameState s, int me)
    {
        double mine = 0, theirs = 0;
        for (int p = 0; p < GameConstants.Players; p++)
        {
            for (int g = 0; g < G; g++)
            {
                int prod = Rules.ProductionOf(s, p, g);
                if (p == me) mine += g == Corn ? 1.5 * prod : 0.6 * prod;
                else theirs += 0.3 * prod;
            }
        }
        double v = mine - theirs;
        return mine > 0 ? Math.Max(v + 1, 0.2) : 0;
    }

    // ---------------------------------------------------------------- Mayor

    private static int CornTiles(GameState s, int me) => s.Tiles[me * T + Corn];
    private static int QuarriesOwned(GameState s, int me) => s.Tiles[me * T + GameConstants.QuarryType];

    private static int EmptyCircles(GameState s, int me)
    {
        int n = 0;
        for (int t = 0; t < T; t++) n += s.Tiles[me * T + t] - s.TilesOcc[me * T + t];
        for (int b = 0; b < B; b++)
            if (s.BuildingOwned[me * B + b] != 0) n += Buildings.Capacity[b] - s.BuildingOcc[me * B + b];
        return n;
    }

    private static double SlotValue(GameState s, int me, int slot)
    {
        if (slot < T)
        {
            if (slot == Corn) return 10;
            if (slot == GameConstants.QuarryType) return 6;
            foreach (int b in Buildings.ProducersOf[slot])
                if (s.BuildingOwned[me * B + b] != 0) return 4 + 0.1 * slot;
            return 1.5;
        }
        int building = slot - T;
        if (Buildings.All[building].IsProduction)
        {
            int good = Buildings.Produces[building];
            return s.Tiles[me * T + good] > 0 ? 3 : 0.5;
        }
        return BuildingValue[building];
    }

    /// <summary>
    /// Pick the best set of circles to fill, then emit the lowest slot of that set (placements must go in slot order,
    /// see Rules.Mayor). Re-deciding after every placement gives the same set again.
    /// </summary>
    private static GameAction ChooseMayorPlacement(GameState s)
    {
        int me = s.Actor;
        int remain = s.MayorRemain;
        Span<double> value = stackalloc double[T + B];
        Span<int> free = stackalloc int[T + B];
        for (int slot = s.MayorLastSlot; slot < T + B; slot++)
        {
            if (slot < T) free[slot] = s.Tiles[me * T + slot] - s.TilesOcc[me * T + slot];
            else
            {
                int b = slot - T;
                free[slot] = s.BuildingOwned[me * B + b] != 0 ? Buildings.Capacity[b] - s.BuildingOcc[me * B + b] : 0;
            }
            value[slot] = free[slot] > 0 ? SlotValue(s, me, slot) : double.NegativeInfinity;
        }

        int lowest = T + B;
        while (remain > 0)
        {
            int bestSlot = -1;
            for (int slot = s.MayorLastSlot; slot < T + B; slot++)
                if (free[slot] > 0 && (bestSlot < 0 || value[slot] > value[bestSlot])) bestSlot = slot;
            if (bestSlot < 0) break;
            int take = Math.Min(free[bestSlot], remain);
            free[bestSlot] -= take;
            remain -= take;
            if (bestSlot < lowest) lowest = bestSlot;
        }
        return new GameAction(ActionType.PlaceColonist, lowest);
    }
}
