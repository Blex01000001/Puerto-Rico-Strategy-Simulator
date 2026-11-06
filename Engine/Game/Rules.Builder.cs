namespace PuertoRico.Engine.Game;

public static partial class Rules
{
    // rules.md section 3 (discounts) and section 4 (Builder, University)

    /// <summary>Cost for a seat: base - min(occupied quarries, tier cap) - 1 for the Builder, never below 0.</summary>
    public static int BuildingCost(GameState s, int seat, int building)
    {
        int quarries = s.TilesOcc[seat * T + GameConstants.QuarryType];
        int cost = Buildings.Cost[building] - Math.Min(quarries, Buildings.Tier[building]);
        if (seat == s.CurrentOwner && s.Phase == Phase.Builder) cost -= 1;
        return Math.Max(cost, 0);
    }

    private static void FillBuilder(GameState s, List<GameAction> a)
    {
        int p = s.Actor;
        int spaceLeft = GameConstants.CitySpaces - s.CitySpacesUsed(p);
        if (spaceLeft <= 0) return; // city full: only Pass (skipped)

        a.Add(GameAction.Pass);
        for (int b = 0; b < B; b++)
        {
            if (s.BuildingSupply[b] <= 0 || s.BuildingOwned[p * B + b] != 0) continue;
            if (Buildings.Spaces[b] > spaceLeft) continue;
            if (BuildingCost(s, p, b) > s.Coins[p]) continue;
            a.Add(new GameAction(ActionType.Build, b));
        }
    }

    private static void ApplyBuilder(GameState s, GameAction a)
    {
        int p = s.Actor;
        if (a.Type == ActionType.Pass) { NextActor(s); return; }
        if (a.Type != ActionType.Build) throw new InvalidOperationException($"{a} is not a Builder action");

        int b = a.A;
        s.Coins[p] -= BuildingCost(s, p, b);
        s.BuildingSupply[b]--;
        bool university = s.HasOccupied(p, BuildingId.University); // checked before the new building exists
        s.BuildingOwned[p * B + b] = 1;
        if (university && TakeSpareColonist(s)) s.BuildingOcc[p * B + b]++;
        NextActor(s);
    }

    private static void CheckCityFull(GameState s)
    {
        for (int p = 0; p < s.PlayerCount; p++)
            if (s.CitySpacesUsed(p) >= GameConstants.CitySpaces) s.EndFlags |= EndFlags.CityFull;
    }
}
