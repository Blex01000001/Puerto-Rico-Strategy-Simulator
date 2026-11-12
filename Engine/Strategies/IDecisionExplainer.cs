using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies;

/// <summary>Search result of one MCTS decision, for display only (replay). Never read by strategies.</summary>
/// <param name="Root">Number of simulations run for this decision.</param>
/// <param name="Actions">Every legal action with its visit count and mean reward (0..1) for the acting seat.</param>
/// <param name="Exploration">UCT exploration constant used by the search (0 when unknown).</param>
/// <param name="RolloutStrategy">Strategy every seat plays after the tree, i.e. how the opponents are modelled in the simulations ("" when unknown).</param>
/// <param name="RolloutRounds">Rounds played after the tree before the players are ranked by points (0 = to the end of the game).</param>
public sealed record SearchSummary(int Simulations, IReadOnlyList<SearchSummary.Entry> Actions, double Exploration = 0, string RolloutStrategy = "", int RolloutRounds = 0)
{
    /// <summary>z value used to call a difference between two mean rewards "more than noise" (about 87 %).</summary>
    public const double NoiseZ = 1.5;

    /// <summary>Traffic light for the chosen action: how it compares with the next most visited actions.</summary>
    public enum PickSignal
    {
        /// <summary>Clearly not luck: beats the compared rival by more than the noise.</summary>
        Green,
        /// <summary>Slightly ahead: no rival is clearly ahead of it, but it does not clearly beat it either (noise in the gap, or too few visits to tell).</summary>
        Yellow,
        /// <summary>A rival has a clearly higher mean reward although the chosen action has more visits (visits not enough, or the reward is low compared with the rival).</summary>
        Red,
    }

    /// <summary>Traffic light of <paramref name="chosen"/> against its <paramref name="rivals"/> (the display passes only the 2nd most visited action).</summary>
    public static PickSignal Assess(Entry chosen, IReadOnlyList<Entry> rivals)
    {
        if (rivals.Count == 0) return PickSignal.Yellow;
        if (rivals.Any(r => ClearlyAhead(r, chosen))) return PickSignal.Red;
        return rivals.All(r => ClearlyAhead(chosen, r)) ? PickSignal.Green : PickSignal.Yellow;
    }

    /// <summary>
    /// True when <paramref name="a"/> beats <paramref name="b"/> by more than the noise: the difference of the mean rewards is larger than
    /// <see cref="NoiseZ"/> × the standard error of that difference (both actions need at least 2 visits).
    /// </summary>
    public static bool ClearlyAhead(Entry a, Entry b)
    {
        if (a.Visits < 2 || b.Visits < 2) return false;
        double se = Math.Sqrt(a.StdError * a.StdError + b.StdError * b.StdError);
        return a.MeanReward - b.MeanReward > NoiseZ * se;
    }

    /// <summary>
    /// UCT score of an action at the end of the search: mean reward + exploration × sqrt(ln(simulations) / visits).
    /// It is what the search compares when it picks the next action to simulate; null for an action never visited.
    /// </summary>
    public double? Uct(Entry e) =>
        e.Visits <= 0 ? null : e.MeanReward + Exploration * Math.Sqrt(Math.Log(Math.Max(1, Simulations)) / e.Visits);

    /// <param name="Line">Principal variation after this action: the most visited reply at each following node (may be empty).</param>
    /// <param name="WinRate">Share of this action's simulations the acting seat won (ties split); with truncated rollouts "won" means leading on points when the simulation stopped.</param>
    /// <param name="StdError">Standard error of the mean reward (sample standard deviation / sqrt(visits)); 0 when unknown.</param>
    public sealed record Entry(GameAction Action, int Visits, double MeanReward, IReadOnlyList<LineStep>? Line = null, double WinRate = 0, double StdError = 0);

    /// <summary>One step of a principal variation: the seat that acts there, its most visited action and that node's visits.</summary>
    public sealed record LineStep(int Seat, GameAction Action, int Visits);
}

/// <summary>Optional: a strategy that can report how it reached its latest decision (the interface <see cref="IStrategy"/> stays unchanged).</summary>
public interface IDecisionExplainer
{
    /// <summary>Summary of the latest <c>ChooseAction</c> call; null when that call needed no search (single legal action).</summary>
    SearchSummary? LastSearch { get; }
}
