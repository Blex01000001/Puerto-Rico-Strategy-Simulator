using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies;

/// <summary>Search result of one MCTS decision, for display only (replay). Never read by strategies.</summary>
/// <param name="Root">Number of simulations run for this decision.</param>
/// <param name="Actions">Every legal action with its visit count and mean reward (0..1) for the acting seat.</param>
public sealed record SearchSummary(int Simulations, IReadOnlyList<SearchSummary.Entry> Actions)
{
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
