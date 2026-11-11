using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies;

/// <summary>Search result of one MCTS decision, for display only (replay). Never read by strategies.</summary>
/// <param name="Root">Number of simulations run for this decision.</param>
/// <param name="Actions">Every legal action with its visit count and mean reward (0..1) for the acting seat.</param>
/// <param name="Exploration">UCT exploration constant used by the search (0 when unknown).</param>
public sealed record SearchSummary(int Simulations, IReadOnlyList<SearchSummary.Entry> Actions, double Exploration = 0)
{
    /// <summary>
    /// UCT score of an action at the end of the search: mean reward + exploration × sqrt(ln(simulations) / visits).
    /// It is what the search compares when it picks the next action to simulate; null for an action never visited.
    /// </summary>
    public double? Uct(Entry e) =>
        e.Visits <= 0 ? null : e.MeanReward + Exploration * Math.Sqrt(Math.Log(Math.Max(1, Simulations)) / e.Visits);

    /// <param name="Line">Principal variation after this action: the most visited reply at each following node (may be empty).</param>
    public sealed record Entry(GameAction Action, int Visits, double MeanReward, IReadOnlyList<LineStep>? Line = null);

    /// <summary>One step of a principal variation: the seat that acts there, its most visited action and that node's visits.</summary>
    public sealed record LineStep(int Seat, GameAction Action, int Visits);
}

/// <summary>Optional: a strategy that can report how it reached its latest decision (the interface <see cref="IStrategy"/> stays unchanged).</summary>
public interface IDecisionExplainer
{
    /// <summary>Summary of the latest <c>ChooseAction</c> call; null when that call needed no search (single legal action).</summary>
    SearchSummary? LastSearch { get; }
}
