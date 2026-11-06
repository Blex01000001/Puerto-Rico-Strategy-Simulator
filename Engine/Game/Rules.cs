namespace PuertoRico.Engine.Game;

/// <summary>
/// Rule engine entry points: list legal actions, apply an action, nothing else mutates a state.
/// After <see cref="Apply"/> the state is always advanced to the next real decision (or game over):
/// actors who have nothing to do, or only "Pass", are skipped automatically.
/// </summary>
public static partial class Rules
{
    private const int P = GameConstants.Players;
    private const int G = GameConstants.GoodCount;
    private const int T = GameConstants.TileTypes;
    private const int B = GameConstants.BuildingCount;

    [ThreadStatic] private static List<GameAction>? t_buf;

    /// <summary>Clears <paramref name="actions"/> and fills it with the legal actions of <see cref="GameState.Actor"/>.</summary>
    public static void GetLegalActions(GameState s, List<GameAction> actions)
    {
        actions.Clear();
        Fill(s, actions);
    }

    public static bool IsLegal(GameState s, GameAction a)
    {
        var buf = new List<GameAction>(32);
        Fill(s, buf);
        return buf.Contains(a);
    }

    /// <summary>Applies a legal action (not validated) and advances to the next decision.</summary>
    public static void Apply(GameState s, GameAction a)
    {
        ApplyCore(s, a);
        Advance(s);
    }

    /// <summary>Like <see cref="Apply"/> but throws if the action is not legal. For tests and debugging.</summary>
    public static void ApplyChecked(GameState s, GameAction a)
    {
        if (!IsLegal(s, a)) throw new InvalidOperationException($"Illegal action {a} in phase {s.Phase} for seat {s.Actor}");
        Apply(s, a);
    }

    /// <summary>Ends the game now with the given reason (used for the round and decision limits).</summary>
    public static void ForceEnd(GameState s, EndFlags reason)
    {
        s.EndFlags |= reason;
        s.Phase = Phase.GameOver;
    }

    private static void Advance(GameState s)
    {
        var buf = t_buf ??= new List<GameAction>(32);
        int guard = 0;
        while (s.Phase != Phase.GameOver)
        {
            buf.Clear();
            Fill(s, buf);
            if (buf.Count == 0) AutoSkip(s);
            else if (buf.Count == 1 && buf[0].Type == ActionType.Pass) ApplyCore(s, buf[0]);
            else break;
            if (++guard > 1_000_000) throw new InvalidOperationException("Advance did not terminate");
        }
    }

    private static void Fill(GameState s, List<GameAction> a)
    {
        switch (s.Phase)
        {
            case Phase.ChooseRole: FillChooseRole(s, a); break;
            case Phase.Settler: FillSettler(s, a); break;
            case Phase.Mayor: FillMayor(s, a); break;
            case Phase.Builder: FillBuilder(s, a); break;
            case Phase.CraftsmanBonus: FillCraftsman(s, a); break;
            case Phase.Trader: FillTrader(s, a); break;
            case Phase.Captain: FillCaptain(s, a); break;
            case Phase.CaptainStorage: FillStorage(s, a); break;
        }
    }

    private static void ApplyCore(GameState s, GameAction a)
    {
        switch (s.Phase)
        {
            case Phase.ChooseRole: StartRole(s, a.A); break;
            case Phase.Settler: ApplySettler(s, a); break;
            case Phase.Mayor: ApplyMayor(s, a); break;
            case Phase.Builder: ApplyBuilder(s, a); break;
            case Phase.CraftsmanBonus: ResolveCraftsman(s, a.A); break;
            case Phase.Trader: ApplyTrader(s, a); break;
            case Phase.Captain: ApplyCaptain(s, a); break;
            case Phase.CaptainStorage: ApplyStorage(s, a); break;
            default: throw new InvalidOperationException("Game is over");
        }
    }

    /// <summary>The actor has nothing to decide: finish their part of the phase.</summary>
    private static void AutoSkip(GameState s)
    {
        switch (s.Phase)
        {
            case Phase.Settler:
            case Phase.Mayor:
            case Phase.Builder:
            case Phase.Trader:
                NextActor(s);
                break;
            case Phase.Captain:
                CaptainSkip(s);
                break;
            case Phase.CaptainStorage:
                FinalizeStorage(s);
                NextActor(s);
                break;
            default:
                throw new InvalidOperationException($"No legal action in phase {s.Phase}");
        }
    }

    // ------------------------------------------------------------------ role selection / flow

    private static void FillChooseRole(GameState s, List<GameAction> a)
    {
        for (int r = 0; r < GameConstants.RoleCount; r++)
            if (s.RoleOwner[r] < 0) a.Add(new GameAction(ActionType.ChooseRole, r));
    }

    private static void StartRole(GameState s, int role)
    {
        int owner = s.Actor;
        s.Coins[owner] += s.RoleCoins[role];
        s.RoleCoins[role] = 0;
        s.RoleOwner[role] = owner;
        s.CurrentRole = role;
        s.CurrentOwner = owner;
        s.ActorsDone = 0;
        s.Actor = owner;

        switch ((Role)role)
        {
            case Role.Settler: s.Phase = Phase.Settler; BeginActor(s); break;
            case Role.Mayor: StartMayor(s); break;
            case Role.Builder: s.Phase = Phase.Builder; BeginActor(s); break;
            case Role.Craftsman: StartCraftsman(s); break;
            case Role.Trader: s.Phase = Phase.Trader; BeginActor(s); break;
            case Role.Captain: StartCaptain(s); break;
        }
    }

    /// <summary>Called whenever the acting seat changes inside a role phase.</summary>
    private static void BeginActor(GameState s)
    {
        switch (s.Phase)
        {
            case Phase.Settler: s.HaciendaUsed = 0; break;
            case Phase.Mayor: BeginMayorActor(s); break;
            case Phase.CaptainStorage: BeginStorageActor(s); break;
        }
    }

    private static void NextActor(GameState s)
    {
        s.ActorsDone++;
        if (s.ActorsDone >= P)
        {
            EndRolePhase(s);
            return;
        }
        s.Actor = (s.Actor + 1) % P;
        BeginActor(s);
    }

    private static void EndRolePhase(GameState s)
    {
        switch ((Role)s.CurrentRole)
        {
            case Role.Settler: DiscardAndFlip(s); break;
            case Role.Mayor: RefillShip(s); break;
            case Role.Builder: CheckCityFull(s); break;
            case Role.Trader: ClearTradeHouseIfFull(s); break;
            case Role.Captain: ClearFullShips(s); break;
        }

        s.ChosenCount++;
        if (s.ChosenCount >= P)
        {
            EndRound(s);
            return;
        }
        s.Phase = Phase.ChooseRole;
        s.Actor = (s.Governor + s.ChosenCount) % P;
    }

    private static void EndRound(GameState s)
    {
        for (int r = 0; r < GameConstants.RoleCount; r++)
        {
            if (s.RoleOwner[r] < 0) s.RoleCoins[r]++;
            s.RoleOwner[r] = -1;
        }
        s.ChosenCount = 0;
        s.Governor = (s.Governor + 1) % P;
        s.Round++;
        s.Actor = s.Governor;
        s.Phase = Phase.ChooseRole;

        if (s.EndFlags != EndFlags.None)
            s.Phase = Phase.GameOver;
        else if (s.Round > s.MaxRounds)
            ForceEnd(s, EndFlags.RoundLimit);
    }

    /// <summary>Hands out VP chips; "chips exhausted" triggers the end of the game (still paid in full).</summary>
    private static void AwardVp(GameState s, int seat, int amount)
    {
        if (amount <= 0) return;
        s.VpChips[seat] += amount;
        s.VpSupply -= amount;
        if (s.VpSupply <= 0)
        {
            s.VpSupply = 0;
            s.EndFlags |= EndFlags.VpExhausted;
        }
    }

    /// <summary>A free colonist from the bank, else from the colonist ship; false if neither has one.</summary>
    private static bool TakeSpareColonist(GameState s)
    {
        if (s.BankColonists > 0) { s.BankColonists--; return true; }
        if (s.ShipColonists > 0) { s.ShipColonists--; return true; }
        return false;
    }
}
