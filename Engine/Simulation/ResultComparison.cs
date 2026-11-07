namespace PuertoRico.Engine.Simulation;

/// <summary>One strategy compared between two result files (A = baseline, B = new). Either side may be missing.</summary>
public sealed class ComparisonRow
{
    public string Key { get; set; } = "";
    public string Strategy { get; set; } = "";
    public StrategyAnalysis? A { get; set; }
    public StrategyAnalysis? B { get; set; }
    public bool HasBoth => A != null && B != null;
    /// <summary>B − A in win share (percentage points as a fraction); 0 when a side is missing.</summary>
    public double DeltaWin => HasBoth ? B!.WinShare - A!.WinShare : 0;
    /// <summary>Half-width of the 95% interval of the difference of two independent estimates.</summary>
    public double DeltaWinCi95 => HasBoth ? Math.Sqrt(A!.WinShareCi95 * A.WinShareCi95 + B!.WinShareCi95 * B.WinShareCi95) : 0;
    /// <summary>True when the difference is larger than its 95% interval (assumes independent samples).</summary>
    public bool Significant => HasBoth && Math.Abs(DeltaWin) > DeltaWinCi95;
    public double DeltaScore => HasBoth ? B!.AvgScore - A!.AvgScore : 0;
}

/// <summary>Side-by-side comparison of two analysed results; strategies are matched by name (and by order when a name repeats).</summary>
public static class ResultComparison
{
    public static List<ComparisonRow> Compare(ResultAnalysis a, ResultAnalysis b)
    {
        static Dictionary<string, StrategyAnalysis> Index(ResultAnalysis r)
        {
            var seen = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            var map = new Dictionary<string, StrategyAnalysis>();
            foreach (var s in r.Strategies)
            {
                seen[s.Strategy] = seen.GetValueOrDefault(s.Strategy) + 1;
                map[$"{s.Strategy.ToLowerInvariant()}#{seen[s.Strategy]}"] = s;
            }
            return map;
        }

        var ia = Index(a);
        var ib = Index(b);
        var keys = ia.Keys.Concat(ib.Keys.Where(k => !ia.ContainsKey(k))).ToList();
        return keys.Select(k => new ComparisonRow
        {
            Key = k,
            Strategy = (ia.GetValueOrDefault(k) ?? ib[k]).Strategy,
            A = ia.GetValueOrDefault(k),
            B = ib.GetValueOrDefault(k),
        }).ToList();
    }
}
