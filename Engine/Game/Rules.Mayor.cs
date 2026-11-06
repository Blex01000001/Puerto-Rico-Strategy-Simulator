namespace PuertoRico.Engine.Game;

public static partial class Rules
{
    // rules.md section 4 (Mayor). Slots: 0..4 plantation of that good, 5 quarry, 6+n building n.
    private const int Slots = T + B;

    private static int SlotFree(GameState s, int seat, int slot)
    {
        if (slot < T) return s.Tiles[seat * T + slot] - s.TilesOcc[seat * T + slot];
        int b = slot - T;
        return s.BuildingOwned[seat * B + b] != 0 ? Buildings.Capacity[b] - s.BuildingOcc[seat * B + b] : 0;
    }

    private static void StartMayor(GameState s)
    {
        int owner = s.CurrentOwner;
        // Privilege: one extra colonist, from the bank only (never from the ship).
        if (s.BankColonists > 0) { s.BankColonists--; s.SanJuan[owner]++; }

        // Hand out the ship one colonist at a time, starting with the Mayor.
        int i = 0;
        while (s.ShipColonists > 0)
        {
            s.SanJuan[(owner + i) % s.PlayerCount]++;
            s.ShipColonists--;
            i++;
        }

        s.Phase = Phase.Mayor;
        s.Actor = owner;
        BeginActor(s);
    }

    /// <summary>Lift every colonist off the board into San Juan; the player then re-places them all.</summary>
    private static void BeginMayorActor(GameState s)
    {
        int p = s.Actor;
        int total = s.ColonistsOnBoard(p);
        for (int t = 0; t < T; t++) s.TilesOcc[p * T + t] = 0;
        for (int b = 0; b < B; b++) s.BuildingOcc[p * B + b] = 0;
        s.SanJuan[p] = total;

        int free = 0;
        for (int slot = 0; slot < Slots; slot++) free += SlotFree(s, p, slot);
        s.MayorRemain = Math.Min(total, free); // must fill every circle unless colonists run out
        s.MayorLastSlot = 0;
    }

    private static void FillMayor(GameState s, List<GameAction> a)
    {
        if (s.MayorRemain <= 0) return;
        int p = s.Actor;
        // Placing in non-decreasing slot order gives each distribution exactly one action sequence.
        // A slot is legal only if the remaining colonists can still all be placed in slots >= it.
        int suffix = 0;
        Span<int> free = stackalloc int[Slots];
        for (int slot = Slots - 1; slot >= s.MayorLastSlot; slot--)
        {
            free[slot] = SlotFree(s, p, slot);
            suffix += free[slot];
        }
        int running = suffix;
        for (int slot = s.MayorLastSlot; slot < Slots; slot++)
        {
            if (free[slot] > 0 && s.MayorRemain <= running)
                a.Add(new GameAction(ActionType.PlaceColonist, slot));
            running -= free[slot];
        }
    }

    private static void ApplyMayor(GameState s, GameAction a)
    {
        if (a.Type != ActionType.PlaceColonist) throw new InvalidOperationException($"{a} is not a Mayor action");
        int p = s.Actor;
        int slot = a.A;
        if (slot < T) s.TilesOcc[p * T + slot]++;
        else s.BuildingOcc[p * B + (slot - T)]++;
        s.SanJuan[p]--;
        s.MayorRemain--;
        s.MayorLastSlot = slot;
        if (s.MayorRemain <= 0) NextActor(s);
    }

    /// <summary>End of Mayor: refill the ship from the bank with max(empty building circles, players).</summary>
    private static void RefillShip(GameState s)
    {
        int empty = 0;
        for (int p = 0; p < s.PlayerCount; p++)
            for (int b = 0; b < B; b++)
                if (s.BuildingOwned[p * B + b] != 0) empty += Buildings.Capacity[b] - s.BuildingOcc[p * B + b];

        int need = Math.Max(empty, s.PlayerCount);
        if (s.BankColonists < need)
        {
            s.ShipColonists += s.BankColonists;
            s.BankColonists = 0;
            s.EndFlags |= EndFlags.ColonistsShort;
        }
        else
        {
            s.BankColonists -= need;
            s.ShipColonists += need;
        }
    }
}
