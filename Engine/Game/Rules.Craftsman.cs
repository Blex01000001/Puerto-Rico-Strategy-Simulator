namespace PuertoRico.Engine.Game;

public static partial class Rules
{
    // rules.md section 4 (Craftsman)

    /// <summary>Goods a seat produces: corn = occupied corn plantations, others = min(occupied plantations, occupied producer circles).</summary>
    public static int ProductionOf(GameState s, int seat, int good)
    {
        int plantations = s.TilesOcc[seat * T + good];
        if (good == (int)Good.Corn) return plantations;
        int circles = 0;
        foreach (int b in Buildings.ProducersOf[good]) circles += s.BuildingOcc[seat * B + b];
        return Math.Min(plantations, circles);
    }

    private static void StartCraftsman(GameState s)
    {
        for (int p = 0; p < s.PlayerCount; p++)
            for (int g = 0; g < G; g++)
                s.Production[p * G + g] = ProductionOf(s, p, g);

        bool any = false;
        for (int g = 0; g < G; g++) if (s.Production[s.CurrentOwner * G + g] > 0) any = true;
        if (!any)
        {
            ResolveCraftsman(s, -1);
            return;
        }
        s.Phase = Phase.CraftsmanBonus;
        s.Actor = s.CurrentOwner;
    }

    private static void FillCraftsman(GameState s, List<GameAction> a)
    {
        for (int g = 0; g < G; g++)
            if (s.Production[s.CurrentOwner * G + g] > 0) a.Add(new GameAction(ActionType.CraftsmanBonus, g));
    }

    /// <summary>
    /// Pay out production starting with the Craftsman, clockwise. Each seat takes everything it is owed
    /// (capped by the supply) before the next one. The privilege good is merged into the Craftsman's take.
    /// </summary>
    private static void ResolveCraftsman(GameState s, int bonusGood)
    {
        for (int i = 0; i < s.PlayerCount; i++)
        {
            int p = (s.CurrentOwner + i) % s.PlayerCount;
            int kinds = 0;
            for (int g = 0; g < G; g++)
            {
                int produced = s.Production[p * G + g];
                if (produced > 0) kinds++;
                int owed = produced + (p == s.CurrentOwner && g == bonusGood ? 1 : 0);
                int take = Math.Min(owed, s.GoodsSupply[g]);
                s.Goods[p * G + g] += take;
                s.GoodsSupply[g] -= take;
            }
            if (s.HasOccupied(p, BuildingId.Factory)) s.Coins[p] += GameConstants.FactoryCoins[kinds];
        }
        Array.Clear(s.Production);
        EndRolePhase(s);
    }
}
