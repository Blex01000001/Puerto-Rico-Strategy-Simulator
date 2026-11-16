namespace PuertoRico.Engine.Game;

/// <summary>Static engine metadata; written into result files (engineVersion, rulesVersion).</summary>
public static class EngineInfo
{
    public const string Version = "0.1.0";
    public const string RulesVersion = "base";

    /// <summary>
    /// Behaviour revision of the engine: bumped BY HAND whenever the same config and seed would give different results
    /// (a rule implementation or interpretation changed, a strategy's decisions changed, MCTS / random use changed).
    /// Refactors and UI changes do not bump it. Written into result files and position dumps; the ML tools put it into
    /// the "recipe fingerprint" of data, models and matches (ml/fingerprint.py) so old data is recognised after a bump.
    /// Files without the field were made with revision 1.
    /// </summary>
    public const int RulesRevision = 1;
}
