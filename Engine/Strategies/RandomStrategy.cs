using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies;

/// <summary>Picks uniformly among the legal actions.</summary>
public sealed class RandomStrategy : IStrategy
{
    private ulong _rng;

    public RandomStrategy(ulong seed) => _rng = seed;

    public GameAction ChooseAction(GameState state, IReadOnlyList<GameAction> legalActions) =>
        legalActions[Rng.NextInt(ref _rng, legalActions.Count)];
}
