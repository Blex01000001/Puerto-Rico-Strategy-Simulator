using PuertoRico.Engine.Events;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Strategies;

namespace Dashboard.Services;

/// <summary>Replay sink that keeps a copy of the state before every decision (so the page can show the board at any step)
/// and the MCTS search summary of that decision, when the acting strategy reported one.</summary>
public sealed class SnapshotEventSink : IGameEventSink
{
    private SearchSummary? _pending;
    public List<GameEvent> Events { get; } = new();
    public List<GameState> Before { get; } = new();
    public List<GameAction> Actions { get; } = new();
    /// <summary>Same length as <see cref="Events"/>; null where the decision involved no search.</summary>
    public List<SearchSummary?> Searches { get; } = new();
    /// <summary>Same length as <see cref="Events"/>; null where the strategy reported no action scores (MCTS, random, forced moves).</summary>
    public List<IReadOnlyList<ScoredAction>?> Scores { get; } = new();
    private IReadOnlyList<ScoredAction>? _pendingScores;
    public bool Enabled => true;

    public void OnScores(IReadOnlyList<ScoredAction> scores) => _pendingScores = scores;

    public void OnSearch(SearchSummary search) => _pending = search;

    public void OnDecision(GameState before, GameAction action)
    {
        Events.Add(new GameEvent(before.Round, before.Phase, before.Actor, action.ToString()));
        Before.Add(before.Clone());
        Actions.Add(action);
        Searches.Add(_pending);
        Scores.Add(_pendingScores);
        _pending = null;
        _pendingScores = null;
    }
}
