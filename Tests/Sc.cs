using PuertoRico.Engine.Game;

namespace PuertoRico.Tests;

/// <summary>Scenario helpers: build a state, mutate it, run real rule transitions.</summary>
internal static class Sc
{
    public const int B = GameConstants.BuildingCount;
    public const int T = GameConstants.TileTypes;
    public const int G = GameConstants.GoodCount;

    public static GameState New(ulong seed = 1) => Setup.NewGame(seed);

    /// <summary>Give a building (colonists taken from the bank).</summary>
    public static void Own(GameState s, int seat, BuildingId b, int occupied = 0)
    {
        s.BuildingOwned[seat * B + (int)b] = 1;
        s.BuildingOcc[seat * B + (int)b] = occupied;
        s.BuildingSupply[(int)b]--;
        s.BankColonists -= occupied;
    }

    /// <summary>Set the number of tiles of a type for a seat (and how many carry colonists).</summary>
    public static void SetTiles(GameState s, int seat, int type, int count, int occupied = 0)
    {
        s.Tiles[seat * T + type] = count;
        s.TilesOcc[seat * T + type] = occupied;
        s.BankColonists -= occupied;
    }

    public static void SetGoods(GameState s, int seat, int good, int n) => s.Goods[seat * G + good] = n;

    public static List<GameAction> Legal(GameState s)
    {
        var l = new List<GameAction>();
        Rules.GetLegalActions(s, l);
        return l;
    }

    public static void Do(GameState s, GameAction a) => Rules.ApplyChecked(s, a);

    public static GameAction A(ActionType t, int a = 0, int b = 0) => new(t, a, b);

    /// <summary>Make <paramref name="owner"/> the governor and have them choose the role (first pick of the round).</summary>
    public static GameState Start(GameState s, int owner, Role role)
    {
        s.Governor = owner;
        s.Actor = owner;
        s.ChosenCount = 0;
        Array.Fill(s.RoleOwner, -1);
        s.Phase = Phase.ChooseRole;
        Do(s, A(ActionType.ChooseRole, (int)role));
        return s;
    }

    /// <summary>Apply Pass for whoever must act until the phase changes (Pass must be legal).</summary>
    public static void PassUntil(GameState s, Phase leaving)
    {
        int guard = 0;
        while (s.Phase == leaving && guard++ < 20) Do(s, GameAction.Pass);
    }

    public static bool Has(List<GameAction> l, ActionType t, int a = -1, int b = -1) =>
        l.Any(x => x.Type == t && (a < 0 || x.A == a) && (b < 0 || x.B == b));

    /// <summary>Play the rest of the round with roles that resolve instantly (no goods, no production).</summary>
    public static void FinishRoundWithIdleRoles(GameState s)
    {
        foreach (var r in new[] { Role.Craftsman, Role.Trader, Role.Captain })
        {
            if (s.Phase != Phase.ChooseRole) break;
            if (s.RoleOwner[(int)r] >= 0) continue;
            Do(s, A(ActionType.ChooseRole, (int)r));
        }
    }
}
