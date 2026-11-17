namespace PuertoRico.Engine.Game;

/// <summary>Static engine metadata; written into result files (engineVersion, rulesVersion).</summary>
public static class EngineInfo
{
    /// <summary>
    /// Product version (SemVer, shown to people, not part of any hash): MINOR for new features, PATCH for fixes that do not
    /// change results; every <see cref="RulesRevision"/> bump is at least a MINOR bump. Change log: docs/versions.json.
    /// </summary>
    public const string Version = "0.4.0";
    public const string RulesVersion = "base";

    /// <summary>
    /// Behaviour revision of the engine: bumped BY HAND whenever the same config and seed would give different results
    /// (a rule implementation or interpretation changed, a strategy's decisions changed, MCTS / random use changed).
    /// Refactors and UI changes do not bump it. Written into result files and position dumps; the ML tools put it into
    /// the "recipe fingerprint" of data, models and matches (ml/fingerprint.py) so old data is recognised after a bump.
    /// Files without the field were made with revision 1.
    /// </summary>
    public const int RulesRevision = 1;

    /// <summary>
    /// The git commit this build was made from ("a1b2c3d4", with "-dirty" when the working tree had uncommitted changes;
    /// "unknown" without git). For tracing only: it is recorded in result files and dumps but never part of a hash.
    /// </summary>
    public static string Commit { get; } = ReadCommit();

    private static string ReadCommit()
    {
        var v = typeof(EngineInfo).Assembly.GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute), false)
            .OfType<System.Reflection.AssemblyInformationalVersionAttribute>().FirstOrDefault()?.InformationalVersion;
        int plus = v?.IndexOf('+') ?? -1;
        return plus >= 0 && plus + 1 < v!.Length ? v[(plus + 1)..] : "unknown";
    }
}
