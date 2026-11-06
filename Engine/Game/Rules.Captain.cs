namespace PuertoRico.Engine.Game;

public static partial class Rules
{
    // rules.md section 4 (Captain, Wharf, storage, ship clearing)

    private static void StartCaptain(GameState s)
    {
        s.Phase = Phase.Captain;
        s.Actor = s.CurrentOwner;
        s.CaptainSkips = 0;
        s.CaptainFirstDone = 0;
        Array.Clear(s.WharfUsed);
    }

    private static int ShipHolding(GameState s, int good)
    {
        for (int i = 0; i < GameConstants.ShipCount; i++)
            if (s.ShipLoad[i] > 0 && s.ShipGood[i] == good) return i;
        return -1;
    }

    /// <summary>Loading is compulsory: if any load is possible the actor must take one (no Pass).</summary>
    private static void FillCaptain(GameState s, List<GameAction> a)
    {
        int p = s.Actor;
        bool wharf = s.WharfUsed[p] == 0 && s.HasOccupied(p, BuildingId.Wharf);
        for (int g = 0; g < G; g++)
        {
            if (s.Goods[p * G + g] <= 0) continue;
            int holding = ShipHolding(s, g);
            if (holding >= 0)
            {
                // The good is already on a ship: it must go there, until that ship is full.
                if (s.ShipLoad[holding] < s.ShipCap[holding])
                    a.Add(new GameAction(ActionType.LoadShip, g, holding));
            }
            else
            {
                for (int ship = 0; ship < GameConstants.ShipCount; ship++)
                    if (s.ShipLoad[ship] == 0) a.Add(new GameAction(ActionType.LoadShip, g, ship));
            }
            if (wharf) a.Add(new GameAction(ActionType.LoadWharf, g));
        }
    }

    private static void ApplyCaptain(GameState s, GameAction a)
    {
        int p = s.Actor;
        int g = a.A;
        int amount;
        if (a.Type == ActionType.LoadShip)
        {
            int ship = a.B;
            amount = Math.Min(s.Goods[p * G + g], s.ShipCap[ship] - s.ShipLoad[ship]);
            s.Goods[p * G + g] -= amount;
            s.ShipLoad[ship] += amount;
            s.ShipGood[ship] = g;
        }
        else if (a.Type == ActionType.LoadWharf)
        {
            amount = s.Goods[p * G + g];
            s.Goods[p * G + g] = 0;
            s.GoodsSupply[g] += amount; // goods on the private ship go straight back to the supply
            s.WharfUsed[p] = 1;
        }
        else throw new InvalidOperationException($"{a} is not a Captain action");

        int vp = amount;
        if (s.HasOccupied(p, BuildingId.Harbor)) vp += 1;
        if (p == s.CurrentOwner && s.CaptainFirstDone == 0) vp += 1;
        if (p == s.CurrentOwner) s.CaptainFirstDone = 1;
        AwardVp(s, p, vp);

        s.CaptainSkips = 0;
        s.Actor = (s.Actor + 1) % s.PlayerCount;
    }

    /// <summary>This actor cannot load; once all three in a row cannot, the shipping part is over.</summary>
    private static void CaptainSkip(GameState s)
    {
        s.CaptainSkips++;
        if (s.CaptainSkips >= s.PlayerCount)
        {
            s.Phase = Phase.CaptainStorage;
            s.ActorsDone = 0;
            s.Actor = s.CurrentOwner;
            BeginActor(s);
            return;
        }
        s.Actor = (s.Actor + 1) % s.PlayerCount;
    }

    // ---- storage: keep whole kinds with warehouses, plus one free barrel ----

    private static void BeginStorageActor(GameState s)
    {
        int p = s.Actor;
        int kinds = 0;
        for (int g = 0; g < G; g++) if (s.Goods[p * G + g] > 0) kinds++;
        int warehouses = (s.HasOccupied(p, BuildingId.SmallWarehouse) ? 1 : 0) + (s.HasOccupied(p, BuildingId.LargeWarehouse) ? 2 : 0);
        // Keeping more can never hurt, so a player always keeps min(warehouse kinds, kinds held) kinds in full.
        s.StoreTarget = Math.Min(warehouses, kinds);
        s.StoreKeptCount = 0;
        s.StoreKeptMask = 0;
        s.StoreLastKept = -1;
        s.StoreBarrel = -1;
    }

    private static int KindsAbove(GameState s, int seat, int good)
    {
        int n = 0;
        for (int g = good + 1; g < G; g++) if (s.Goods[seat * G + g] > 0) n++;
        return n;
    }

    private static void FillStorage(GameState s, List<GameAction> a)
    {
        int p = s.Actor;
        if (s.StoreKeptCount < s.StoreTarget)
        {
            int needAfter = s.StoreTarget - s.StoreKeptCount - 1;
            for (int g = s.StoreLastKept + 1; g < G; g++)
                if (s.Goods[p * G + g] > 0 && KindsAbove(s, p, g) >= needAfter)
                    a.Add(new GameAction(ActionType.KeepGoods, g));
            return;
        }
        if (s.StoreBarrel >= 0) return;
        for (int g = 0; g < G; g++)
            if (s.Goods[p * G + g] > 0 && (s.StoreKeptMask & (1 << g)) == 0)
                a.Add(new GameAction(ActionType.KeepBarrel, g));
    }

    private static void ApplyStorage(GameState s, GameAction a)
    {
        if (a.Type == ActionType.KeepGoods)
        {
            s.StoreKeptMask |= 1 << a.A;
            s.StoreKeptCount++;
            s.StoreLastKept = a.A;
        }
        else if (a.Type == ActionType.KeepBarrel)
        {
            s.StoreBarrel = a.A;
        }
        else throw new InvalidOperationException($"{a} is not a storage action");
    }

    /// <summary>Everything not kept goes back to the supply.</summary>
    private static void FinalizeStorage(GameState s)
    {
        int p = s.Actor;
        for (int g = 0; g < G; g++)
        {
            int have = s.Goods[p * G + g];
            if (have == 0) continue;
            int keep = (s.StoreKeptMask & (1 << g)) != 0 ? have : (s.StoreBarrel == g ? 1 : 0);
            s.Goods[p * G + g] = keep;
            s.GoodsSupply[g] += have - keep;
        }
    }

    /// <summary>Ships that are completely full are emptied at the end of the Captain phase.</summary>
    private static void ClearFullShips(GameState s)
    {
        for (int i = 0; i < GameConstants.ShipCount; i++)
        {
            if (s.ShipLoad[i] < s.ShipCap[i]) continue;
            s.GoodsSupply[s.ShipGood[i]] += s.ShipLoad[i];
            s.ShipLoad[i] = 0;
            s.ShipGood[i] = -1;
        }
    }
}
