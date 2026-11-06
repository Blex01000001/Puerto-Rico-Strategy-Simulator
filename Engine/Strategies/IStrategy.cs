using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies;

/// <summary>
/// A player. Random, hand-written rules and MCTS all implement this one interface.
/// Convention: a strategy must not read opponents' VP chips (<see cref="GameState.VpChips"/>); they are hidden
/// information. MCTS may use the full state internally. The acting seat is <see cref="GameState.Actor"/>.
/// </summary>
public interface IStrategy
{
    GameAction ChooseAction(GameState state, IReadOnlyList<GameAction> legalActions);
}
