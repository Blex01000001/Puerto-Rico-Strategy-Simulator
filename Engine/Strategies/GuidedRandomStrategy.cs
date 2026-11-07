using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies;

/// <summary>
/// Random, but weighted by action type so it rarely wastes a turn: passing is unlikely, shipping, building, selling and
/// taking plantations are favoured. Costs about the same as <see cref="RandomStrategy"/>; used as an MCTS rollout policy.
/// </summary>
public sealed class GuidedRandomStrategy : IStrategy
{
    private ulong _rng;
    private readonly double[] _w = new double[64];

    public GuidedRandomStrategy(ulong seed) => _rng = seed;

    private static double Weight(ActionType t) => t switch
    {
        ActionType.Pass => 0.25,
        ActionType.LoadShip or ActionType.LoadWharf => 4,
        ActionType.Build or ActionType.Sell or ActionType.TakePlantation or ActionType.TakeQuarry or ActionType.UseHacienda => 2,
        _ => 1,
    };

    public GameAction ChooseAction(GameState state, IReadOnlyList<GameAction> legalActions)
    {
        int n = legalActions.Count;
        var w = n <= _w.Length ? _w : new double[n];
        double total = 0;
        for (int i = 0; i < n; i++) total += w[i] = Weight(legalActions[i].Type);
        double r = (Rng.Next(ref _rng) >> 11) * (1.0 / (1UL << 53)) * total;
        for (int i = 0; i < n; i++)
        {
            r -= w[i];
            if (r < 0) return legalActions[i];
        }
        return legalActions[n - 1];
    }
}
