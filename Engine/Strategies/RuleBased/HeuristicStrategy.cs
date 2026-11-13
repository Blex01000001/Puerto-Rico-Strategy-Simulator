using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// Base class for hand-written score-based strategies. Every legal action gets a score from the hooks below and the
/// highest score wins (ties go to the first legal action, so play is deterministic). Mayor placement is decided
/// as a whole set of circles and then emitted in slot order (see Rules.Mayor). Only public information is read:
/// never opponents' VP chips. The defaults describe the "corn shipper"; subclasses override the hooks they care about.
/// </summary>
public abstract class HeuristicStrategy : IStrategy, IScoreExplainer
{
    protected const int T = GameConstants.TileTypes;
    protected const int B = GameConstants.BuildingCount;
    protected const int G = GameConstants.GoodCount;
    protected const int Corn = (int)Good.Corn;
    protected const int Quarry = GameConstants.QuarryType;

    /// <summary>Baseline worth of owning/manning a building for a shipping-oriented player.</summary>
    protected static readonly double[] BaseBuildingValue = BuildValues();

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

    /// <summary>Minimum building value worth paying for (config param <c>buildThreshold</c>).</summary>
    protected double BuildThreshold { get; private set; }

    private readonly IReadOnlyDictionary<string, JsonElement> _parameters;
    private readonly double _defaultThreshold4;
    private readonly double _defaultThreshold3;
    private int _players;

    /// <param name="defaultBuildThreshold">Default <c>buildThreshold</c> for 4 players (and for 3 when no 3-player value is given).</param>
    /// <param name="defaultBuildThreshold3p">Default <c>buildThreshold</c> for 3 players, when it differs.</param>
    protected HeuristicStrategy(IReadOnlyDictionary<string, JsonElement> parameters, double defaultBuildThreshold = 5.0, double? defaultBuildThreshold3p = null)
    {
        _parameters = parameters;
        _defaultThreshold4 = defaultBuildThreshold;
        _defaultThreshold3 = defaultBuildThreshold3p ?? defaultBuildThreshold;
    }

    /// <summary>
    /// Called once, at the first decision, when the player count is known. Subclasses read their parameters here
    /// with <see cref="Param"/> so defaults can differ between 3 and 4 players; parameters written in the config always win.
    /// </summary>
    protected virtual void Configure(int players) { }

    /// <summary>Config parameter <paramref name="key"/>, else the default for this player count.</summary>
    protected double Param(string key, int players, double default3p, double default4p) =>
        StrategyRegistry.GetDouble(_parameters, key, players == 3 ? default3p : default4p);

    /// <summary>Seed for the optional random tie-break (set by <see cref="StrategyRegistry"/> from the game seed and the seat).</summary>
    public ulong Seed { get; set; }
    private ulong _tieRng;
    private int _tieMode;

    public bool RecordScores { get; set; }
    public IReadOnlyList<ScoredAction>? LastScores { get; private set; }

    public GameAction ChooseAction(GameState s, IReadOnlyList<GameAction> legalActions)
    {
        LastScores = null;
        if (_players == 0)
        {
            _players = s.PlayerCount;
            BuildThreshold = StrategyRegistry.GetDouble(_parameters, "buildThreshold", _players == 3 ? _defaultThreshold3 : _defaultThreshold4);
            // experimental, off by default: equal top scores are broken at random in 1 = the Settler and Craftsman-bonus phases, 2 = every phase but Mayor,
            // 3 = the Settler phase only, 4 = the Craftsman bonus only
            // (default 0: the first action in engine order wins, the behaviour of every published result). docs/strategy-analysis.md section 8.
            _tieMode = (int)StrategyRegistry.GetDouble(_parameters, "randomTies", 0);
            _tieRng = Seed;
            Configure(_players);
        }
        if (legalActions.Count == 1) return legalActions[0];
        if (s.Phase == Phase.Mayor)
        {
            // the Mayor set is chosen as a whole (see ChooseMayorPlacement); the reported score of an action is the value of its circle
            if (RecordScores)
            {
                var slots = new List<ScoredAction>(legalActions.Count);
                foreach (var a in legalActions) slots.Add(new ScoredAction(a, SlotValue(s, s.Actor, a.A)));
                LastScores = slots;
            }
            return ChooseMayorPlacement(s);
        }

        int me = s.Actor;
        int best = 0;
        double bestScore = double.NegativeInfinity;
        List<ScoredAction>? recorded = RecordScores ? new List<ScoredAction>(legalActions.Count) : null;
        bool randomTie = _tieMode == 2
                         || (_tieMode == 1 && (s.Phase == Phase.Settler || s.Phase == Phase.CraftsmanBonus))
                         || (_tieMode == 3 && s.Phase == Phase.Settler)
                         || (_tieMode == 4 && s.Phase == Phase.CraftsmanBonus);
        int tied = 0;
        for (int i = 0; i < legalActions.Count; i++)
        {
            double score = Score(s, me, legalActions[i]);
            recorded?.Add(new ScoredAction(legalActions[i], score));
            if (score > bestScore) { bestScore = score; best = i; tied = 1; }
            else if (randomTie && score == bestScore)
            {
                tied++; // reservoir sampling: every action of the tied top group ends up chosen with the same probability
                if (Rng.NextInt(ref _tieRng, tied) == 0) best = i;
            }
        }
        LastScores = recorded;
        return legalActions[best];
    }

    private double Score(GameState s, int me, GameAction a)
    {
        switch (a.Type)
        {
            case ActionType.ChooseRole: return RoleValue(s, me, (Role)a.A);
            case ActionType.TakePlantation: return TileValue(s, me, a.A);
            case ActionType.TakeQuarry: return QuarryValue(s, me);
            case ActionType.UseHacienda: return 20;
            case ActionType.Pass:
                return s.Phase switch
                {
                    Phase.Builder => BuildThreshold,
                    Phase.Settler => 0.5,
                    _ => 1.0,
                };
            case ActionType.Build: return BuildingWanted(s, me, a.A) - 0.01 * Buildings.Cost[a.A];
            case ActionType.CraftsmanBonus: return BonusGoodValue(s, me, a.A);
            case ActionType.Sell: return SellValue(s, me, a.A);
            case ActionType.LoadShip:
                {
                    int room = s.ShipCap[a.B] - s.ShipLoad[a.B];
                    int vp = Math.Min(s.Goods[me * G + a.A], room);
                    return vp * 10 + ShipGoodBias(s, me, a.A) - s.ShipCap[a.B] * 0.01;
                }
            case ActionType.LoadWharf:
                return WharfLoadValue(s, me, a.A, s.Goods[me * G + a.A]);
            case ActionType.KeepGoods: return KeepValue(s, me, a.A, s.Goods[me * G + a.A]);
            case ActionType.KeepBarrel: return KeepValue(s, me, a.A, 1);
            default: return 0;
        }
    }

    // ------------------------------------------------------------------ hooks (defaults = corn shipper)

    protected virtual double TileValue(GameState s, int me, int good) =>
        good == Corn ? 10 : 2 + 0.1 * good + (CornTiles(s, me) >= 8 ? 3 : 0);

    /// <summary>Tie-break added to the score of loading a good (10 points per barrel come first): positive = ship it first.</summary>
    protected virtual double ShipGoodBias(GameState s, int me, int good) => good == Corn ? 1 : 0;

    /// <summary>Score of putting all <paramref name="count"/> barrels of a good on the private Wharf ship (a public ship scores barrels × 10).</summary>
    protected virtual double WharfLoadValue(GameState s, int me, int good, int count) => count * 10 + ShipGoodBias(s, me, good) - 0.5;

    protected virtual double QuarryValue(GameState s, int me) => QuarriesOwned(s, me) >= 3 ? 3 : 6.5;

    /// <summary>Value of owning this building: used for buying it and for the Builder role.</summary>
    protected virtual double BuildingWanted(GameState s, int me, int building) => BaseBuildingValue[building];

    /// <summary>Value of putting one colonist on a circle (slot: 0..4 plantation, 5 quarry, 6+n building n).</summary>
    protected virtual double SlotValue(GameState s, int me, int slot)
    {
        if (slot < T)
        {
            if (slot == Corn) return 10;
            if (slot == Quarry) return 6;
            foreach (int b in Buildings.ProducersOf[slot])
                if (s.BuildingOwned[me * B + b] != 0) return 4 + 0.1 * slot;
            return 1.5;
        }
        int building = slot - T;
        if (Buildings.All[building].IsProduction)
            return s.Tiles[me * T + Buildings.Produces[building]] > 0 ? 3 : 0.5;
        return BaseBuildingValue[building];
    }

    protected virtual double BonusGoodValue(GameState s, int me, int good) => good == Corn ? 10 : 1 + good;

    protected virtual double SellValue(GameState s, int me, int good) =>
        good == Corn ? 0.5 : 2 + GameConstants.BasePrice[good];

    protected virtual double KeepValue(GameState s, int me, int good, int count) =>
        good == Corn ? 100 : count * (GameConstants.BasePrice[good] + 1);

    /// <summary>How much one barrel produced of this good is worth when judging the Craftsman role.</summary>
    protected virtual double ProductionWeight(GameState s, int me, int good) => good == Corn ? 1.5 : 0.6;

    protected virtual double SettlerRoleValue(GameState s, int me)
    {
        int tiles = s.TileCount(me);
        return tiles >= GameConstants.MaxTiles ? 0 : 5 + (CornTiles(s, me) < 6 ? 2 : 0) - (tiles >= 9 ? 2 : 0);
    }

    protected virtual double MayorRoleValue(GameState s, int me)
    {
        int gain = Math.Min(EmptyCircles(s, me), s.SanJuan[me] + 1 + s.ShipColonists / s.PlayerCount);
        return 1 + 1.6 * gain;
    }

    protected virtual double TraderRoleValue(GameState s, int me)
    {
        int others = 0;
        for (int g = 1; g < G; g++) others += s.Goods[me * G + g];
        return others > 0 ? 2.5 : 0.3;
    }

    protected virtual double CaptainRoleValue(GameState s, int me)
    {
        int corn = s.Goods[me * G + Corn];
        int total = s.GoodTotal(me);
        if (total == 0) return 0;
        int room = CornRoom(s);
        int loadable = Math.Min(corn, room);
        if (s.HasOccupied(me, BuildingId.Wharf)) loadable = Math.Max(loadable, corn);
        if (loadable == 0) loadable = Math.Min(total - corn, 2); // other goods can still be shipped
        if (loadable == 0) return 0;
        return 3 + loadable * 1.2 + 1 + (s.HasOccupied(me, BuildingId.Harbor) ? 2 : 0);
    }

    /// <summary>Prospector (4 players only): one coin and nothing else.</summary>
    protected virtual double ProspectorRoleValue(GameState s, int me) => 1.0 * RoleCoinWeight(s, me);

    /// <summary>Extra weight on the coins lying on a role card.</summary>
    protected virtual double RoleCoinWeight(GameState s, int me) => 1.0;

    // ------------------------------------------------------------------ shared logic

    protected double RoleValue(GameState s, int me, Role role)
    {
        double v;
        switch (role)
        {
            case Role.Captain: v = CaptainRoleValue(s, me); break;
            case Role.Craftsman: v = CraftsmanRoleValue(s, me); break;
            case Role.Settler: v = SettlerRoleValue(s, me); break;
            case Role.Mayor: v = MayorRoleValue(s, me); break;
            case Role.Builder: v = BuilderRoleValue(s, me); break;
            case Role.Prospector: v = ProspectorRoleValue(s, me); break;
            default: v = TraderRoleValue(s, me); break;
        }
        return v + s.RoleCoins[(int)role] * RoleCoinWeight(s, me);
    }

    private double BuilderRoleValue(GameState s, int me)
    {
        double bestValue = 0;
        for (int b = 0; b < B; b++)
        {
            if (s.BuildingOwned[me * B + b] != 0 || s.BuildingSupply[b] <= 0) continue;
            int cost = Math.Max(0, Buildings.Cost[b] - Math.Min(s.TilesOcc[me * T + Quarry], Buildings.Tier[b]) - 1);
            if (cost > s.Coins[me] || Buildings.Spaces[b] > GameConstants.CitySpaces - s.CitySpacesUsed(me)) continue;
            double w = BuildingWanted(s, me, b);
            if (w > bestValue) bestValue = w;
        }
        return bestValue >= BuildThreshold ? Math.Min(bestValue - 1, 14) : 0.5;
    }

    private double CraftsmanRoleValue(GameState s, int me)
    {
        double mine = 0, theirs = 0;
        for (int p = 0; p < s.PlayerCount; p++)
        {
            for (int g = 0; g < G; g++)
            {
                int prod = Rules.ProductionOf(s, p, g);
                if (p == me) mine += ProductionWeight(s, me, g) * prod;
                else theirs += 0.3 * prod;
            }
        }
        return mine > 0 ? Math.Max(mine - theirs + 1, 0.2) : 0;
    }

    protected static int CornTiles(GameState s, int me) => s.Tiles[me * T + Corn];
    protected static int QuarriesOwned(GameState s, int me) => s.Tiles[me * T + Quarry];

    protected static int EmptyCircles(GameState s, int me)
    {
        int n = 0;
        for (int t = 0; t < T; t++) n += s.Tiles[me * T + t] - s.TilesOcc[me * T + t];
        for (int b = 0; b < B; b++)
            if (s.BuildingOwned[me * B + b] != 0) n += Buildings.Capacity[b] - s.BuildingOcc[me * B + b];
        return n;
    }

    /// <summary>Barrels of this good that could still be loaded on public ships (0 if the good is stuck on a full ship).</summary>
    protected static int ShipRoom(GameState s, int good)
    {
        for (int i = 0; i < GameConstants.ShipCount; i++)
            if (s.ShipLoad[i] > 0 && s.ShipGood[i] == good) return s.ShipCap[i] - s.ShipLoad[i];
        int room = 0;
        for (int i = 0; i < GameConstants.ShipCount; i++)
            if (s.ShipLoad[i] == 0) room = Math.Max(room, s.ShipCap[i]);
        return room;
    }

    private static int CornRoom(GameState s) => ShipRoom(s, Corn);

    /// <summary>Pick the best set of circles to fill, then emit the lowest slot of that set.</summary>
    private GameAction ChooseMayorPlacement(GameState s)
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
