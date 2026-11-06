using System.Text.Json;

namespace PuertoRico.Engine.Simulation;

/// <summary>
/// Parameter sweep: vary the numeric <c>params</c> of one seat (the target) over a grid, play the same games
/// against the other seats for every grid point, and compare. All points use the same master seed, so the
/// compared games share their random draws (common random numbers) and differences are less noisy.
/// </summary>
public sealed class SweepConfig
{
    /// <summary>Id of the seat whose strategy parameters are varied.</summary>
    public string Target { get; set; } = "";
    /// <summary>Games per grid point; 0 = use <c>games</c> of the main config.</summary>
    public int GamesPerPoint { get; set; }
    /// <summary>Parameter name -> list of values; the grid is the cartesian product.</summary>
    public Dictionary<string, List<double>> Parameters { get; set; } = new();
}

public sealed class SweepPoint
{
    public Dictionary<string, double> Params { get; set; } = new();
    public int Games { get; set; }
    public double WinShare { get; set; }
    /// <summary>Half-width of the 95% confidence interval of <see cref="WinShare"/>.</summary>
    public double WinShareCi95 { get; set; }
    public double AvgScore { get; set; }
    public double StdScore { get; set; }
    /// <summary>All seats at this point (the opponents' results too).</summary>
    public List<SeatSummary> Seats { get; set; } = new();
}

public sealed class SweepResult
{
    public int SchemaVersion { get; set; } = 1;
    public string EngineVersion { get; set; } = Game.EngineInfo.Version;
    /// <summary>running | completed | cancelled</summary>
    public string Status { get; set; } = "running";
    public DateTime StartedUtc { get; set; }
    public DateTime? FinishedUtc { get; set; }
    public SimulationConfig Config { get; set; } = new();
    public string Target { get; set; } = "";
    public int PointsPlanned { get; set; }
    public List<SweepPoint> Points { get; set; } = new();
    /// <summary>Index into <see cref="Points"/> of the best win share so far, or -1.</summary>
    public int BestIndex { get; set; } = -1;
}

public static class SweepRunner
{
    /// <summary>Grid points in a fixed order (parameter names sorted, values in the order given).</summary>
    public static List<Dictionary<string, double>> Grid(SweepConfig sweep)
    {
        var names = sweep.Parameters.Keys.OrderBy(k => k, StringComparer.Ordinal).ToList();
        var points = new List<Dictionary<string, double>> { new() };
        foreach (var name in names)
        {
            var next = new List<Dictionary<string, double>>();
            foreach (var partial in points)
                foreach (double v in sweep.Parameters[name])
                    next.Add(new Dictionary<string, double>(partial) { [name] = v });
            points = next;
        }
        return points;
    }

    public static void Validate(SimulationConfig cfg)
    {
        cfg.Validate();
        var sweep = cfg.Sweep ?? throw new InvalidDataException("The config has no \"sweep\" section.");
        if (!cfg.Seats.Any(s => s.Id == sweep.Target))
            throw new InvalidDataException($"sweep.target '{sweep.Target}' is not a seat id.");
        if (sweep.Parameters.Count == 0 || sweep.Parameters.Values.Any(v => v.Count == 0))
            throw new InvalidDataException("sweep.parameters needs at least one parameter with at least one value.");
    }

    public static SweepResult Run(SimulationConfig cfg, string? outPath, IProgress<string>? log, CancellationToken ct)
    {
        Validate(cfg);
        var sweep = cfg.Sweep!;
        var grid = Grid(sweep);
        int games = sweep.GamesPerPoint > 0 ? sweep.GamesPerPoint : cfg.Games;
        var result = new SweepResult { StartedUtc = DateTime.UtcNow, Config = cfg, Target = sweep.Target, PointsPlanned = grid.Count };

        foreach (var values in grid)
        {
            if (ct.IsCancellationRequested) break;
            var point = SimulationConfig.Clone(cfg);
            point.Sweep = null;
            point.Games = games;
            point.Output.PerGameRecords = false;
            var target = point.Seats.First(s => s.Id == sweep.Target);
            foreach (var (name, value) in values)
                target.Params[name] = JsonSerializer.SerializeToElement(value);

            var run = BatchSimulator.Run(point, new BatchOptions(), ct);
            if (run.Status == "cancelled") break; // partial point: do not report it

            var mine = run.Summary.First(s => s.SeatId == sweep.Target);
            result.Points.Add(new SweepPoint
            {
                Params = values,
                Games = run.GamesCompleted,
                WinShare = mine.WinShare,
                WinShareCi95 = ResultAnalysis.Ci(mine.WinShare, mine.Games),
                AvgScore = mine.AvgScore,
                StdScore = mine.StdScore,
                Seats = run.Summary,
            });
            result.BestIndex = Enumerable.Range(0, result.Points.Count).MaxBy(i => result.Points[i].WinShare);
            log?.Report($"point {result.Points.Count}/{grid.Count}: {Describe(values)} -> win {mine.WinShare:P1}");
            if (outPath != null) Write(result, outPath);
        }

        result.Status = result.Points.Count == grid.Count ? "completed" : "cancelled";
        result.FinishedUtc = DateTime.UtcNow;
        if (outPath != null) Write(result, outPath);
        return result;
    }

    public static string Describe(Dictionary<string, double> values) =>
        string.Join(", ", values.OrderBy(kv => kv.Key, StringComparer.Ordinal).Select(kv => $"{kv.Key}={kv.Value:0.##}"));

    public static void Write(SweepResult result, string path)
    {
        string? dir = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        string tmp = path + ".tmp";
        using (var fs = File.Create(tmp)) JsonSerializer.Serialize(fs, result, SimulationConfig.JsonOptions);
        File.Move(tmp, path, overwrite: true);
    }
}
