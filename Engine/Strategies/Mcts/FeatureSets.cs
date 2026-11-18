using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.Mcts;

/// <summary>
/// A versioned list of position features. Several versions live side by side: a value model (trained offline) records
/// the feature names it was trained on, and the engine picks the set that matches them (<see cref="FeatureSets.Find"/>),
/// so models and data of an older version keep working after a new version is added. A version is never edited once models
/// or data exist for it: a different list is a new version.
/// </summary>
public abstract class FeatureSet
{
    public abstract int Version { get; }
    public abstract IReadOnlyList<string> Names { get; }
    public int Count => Names.Count;

    /// <summary>Scratch buffer length for <see cref="ExtractAll"/>.</summary>
    public abstract int ScratchLength { get; }

    /// <summary>
    /// Fills one row per seat (rows[seat] = features from that seat's point of view; rows needs at least
    /// <c>s.PlayerCount</c> arrays of length <see cref="Count"/>).
    /// </summary>
    public abstract void ExtractAll(GameState s, float[][] rows, float[] seatScratch);

    /// <summary>Features of one seat (allocates; tests and tools only).</summary>
    public float[] Extract(GameState s, int me)
    {
        var rows = new float[GameConstants.MaxPlayers][];
        for (int i = 0; i < rows.Length; i++) rows[i] = new float[Count];
        ExtractAll(s, rows, new float[ScratchLength]);
        return rows[me];
    }
}

public static class FeatureSets
{
    /// <summary>The newest feature set: what position dumps use unless a version is asked for. Read by ml/fingerprint.py (keep the literal).</summary>
    public const int LatestVersion = 2;

    private sealed class V1Set : FeatureSet
    {
        public override int Version => FeaturesV1.Version;
        public override IReadOnlyList<string> Names => FeaturesV1.Names;
        public override int ScratchLength => FeaturesV1.ScratchLength;
        public override void ExtractAll(GameState s, float[][] rows, float[] seatScratch) => FeaturesV1.ExtractAll(s, rows, seatScratch);
    }

    private sealed class V2Set : FeatureSet
    {
        public override int Version => FeaturesV2.Version;
        public override IReadOnlyList<string> Names => FeaturesV2.Names;
        public override int ScratchLength => FeaturesV2.ScratchLength;
        public override void ExtractAll(GameState s, float[][] rows, float[] seatScratch) => FeaturesV2.ExtractAll(s, rows, seatScratch);
    }

    public static readonly FeatureSet V1 = new V1Set();
    public static readonly FeatureSet V2 = new V2Set();

    /// <summary>Every feature set the engine can read models and data of, oldest first.</summary>
    public static readonly IReadOnlyList<FeatureSet> All = new[] { V1, V2 };

    public static FeatureSet Latest => Get(LatestVersion);

    public static string SupportedText => string.Join(", ", All.Select(f => f.Version));

    public static FeatureSet Get(int version) =>
        All.FirstOrDefault(f => f.Version == version)
        ?? throw new ArgumentException($"unknown feature version {version} (supported: {SupportedText})");

    /// <summary>The feature set whose names are exactly <paramref name="names"/>, or null.</summary>
    public static FeatureSet? Find(IReadOnlyList<string> names) =>
        All.FirstOrDefault(f => f.Names.Count == names.Count && f.Names.SequenceEqual(names));
}
