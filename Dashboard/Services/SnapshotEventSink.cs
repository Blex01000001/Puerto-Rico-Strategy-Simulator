using PuertoRico.Engine.Events;
using PuertoRico.Engine.Game;

namespace Dashboard.Services;

/// <summary>Replay sink that keeps a copy of the state before every decision, so the page can show the board at any step.</summary>
public sealed class SnapshotEventSink : IGameEventSink
{
    public List<GameEvent> Events { get; } = new();
    public List<GameState> Before { get; } = new();
    public bool Enabled => true;

    public void OnDecision(GameState before, GameAction action)
    {
        Events.Add(new GameEvent(before.Round, before.Phase, before.Actor, action.ToString()));
        Before.Add(before.Clone());
    }
}
