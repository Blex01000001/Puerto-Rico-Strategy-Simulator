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

        s.Phase = Phase.CraftsmanBonus;
        s.Actor = s.CurrentOwner;
        var options = new List<GameAction>(G + 1);
        FillCraftsman(s, options);
        if (options.Count == 0)
        {
            ResolveCraftsman(s, -1); // nothing to choose: no good the Craftsman produces has a barrel left over for the privilege
            return;
        }
    }

    /// <summary>
    /// rules.md section 4 (Craftsman): the privilege is optional ("may take"): 1 extra barrel of a good the Craftsman produces,
    /// only when the supply still holds a barrel after his normal production (he collects first). Pass = decline.
    /// No such good: the phase is skipped.
    /// </summary>
    private static void FillCraftsman(GameState s, List<GameAction> a)
    {
        int owner = s.CurrentOwner;
        for (int g = 0; g < G; g++)
        {
            int produced = s.Production[owner * G + g];
            if (produced > 0 && s.GoodsSupply[g] > produced) a.Add(new GameAction(ActionType.CraftsmanBonus, g));
        }
        if (a.Count > 0) a.Add(GameAction.Pass);
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
                int owed = produced + (p == s.CurrentOwner && g == bonusGood ? 1 : 0);
                int take = Math.Min(owed, s.GoodsSupply[g]);
                if (take > 0) kinds++; // rules.md section 3 (Factory): a kind counts only when the seat really received barrels of it
                s.Goods[p * G + g] += take;
                s.GoodsSupply[g] -= take;
            }
            if (s.HasOccupied(p, BuildingId.Factory)) s.Coins[p] += GameConstants.FactoryCoins[kinds];
        }
        Array.Clear(s.Production);
        EndRolePhase(s);
    }
}
