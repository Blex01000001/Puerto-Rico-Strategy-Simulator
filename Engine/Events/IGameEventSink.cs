using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Events;

/// <summary>Receives every decision of a game. Mass simulations use <see cref="NullEventSink"/>; single-game replay uses <see cref="ListEventSink"/>.</summary>
public interface IGameEventSink
{
    bool Enabled { get; }
    void OnDecision(GameState before, GameAction action);
}

public sealed class NullEventSink : IGameEventSink
{
    public static readonly NullEventSink Instance = new();
    public bool Enabled => false;
    public void OnDecision(GameState before, GameAction action) { }
}

public sealed record GameEvent(int Round, Phase Phase, int Seat, string Action);

public sealed class ListEventSink : IGameEventSink
{
    public List<GameEvent> Events { get; } = new();
    public bool Enabled => true;
    public void OnDecision(GameState before, GameAction action) =>
        Events.Add(new GameEvent(before.Round, before.Phase, before.Actor, action.ToString()));
}
