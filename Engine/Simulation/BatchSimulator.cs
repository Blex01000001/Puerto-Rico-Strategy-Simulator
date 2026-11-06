using System.Diagnostics;
using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Simulation;

public sealed record SimProgress(int Completed, int Total, TimeSpan Elapsed)
{
    public double GamesPerSecond => Elapsed.TotalSeconds > 0 ? Completed / Elapsed.TotalSeconds : 0;
}

public sealed class BatchOptions
{
    /// <summary>Result file; checkpoints and the final result are written here (atomically).</summary>
    public string? OutPath { get; set; }
    /// <summary>Games already played by an earlier run of the same config (see <see cref="BatchSimulator.LoadForResume"/>).</summary>
    public SimulationResult? ResumeFrom { get; set; }
    public IProgress<SimProgress>? Progress { get; set; }
}

public static class BatchSimulator
{
    public static SimulationResult Run(SimulationConfig cfg, BatchOptions options, CancellationToken ct)
    {
        cfg.Validate();
        int total = cfg.Games;
        var records = new GameRecord?[total];
        int done = 0;
        var started = DateTime.UtcNow;

        if (options.ResumeFrom != null)
        {
            EnsureCompatible(cfg, options.ResumeFrom.Config);
            if (options.ResumeFrom.Games.Any(g => g.Players.Any(p => p.Buildings == null)))
                throw new InvalidDataException("The result file was written by an older version (no per-player building data); cannot resume it.");
            started = options.ResumeFrom.StartedUtc;
            foreach (var g in options.ResumeFrom.Games)
                if (g.Index >= 0 && g.Index < total && records[g.Index] == null) { records[g.Index] = g; done++; }
        }

        var pending = Enumerable.Range(0, total).Where(i => records[i] == null).ToArray();
        var clock = Stopwatch.StartNew();
        var gate = new object();
        long lastCheckpointTicks = clock.ElapsedTicks;
        int lastCheckpointDone = done;
        long lastProgressMs = -1000;

        var po = new ParallelOptions
        {
            CancellationToken = ct,
            MaxDegreeOfParallelism = cfg.Parallelism.MaxDegree <= 0 ? Environment.ProcessorCount : cfg.Parallelism.MaxDegree,
        };

        bool cancelled = false;
        try
        {
            Parallel.ForEach(pending, po, index =>
            {
                var record = GameRunner.Play(cfg, index);
                records[index] = record;
                int n = Interlocked.Increment(ref done);

                long ms = clock.ElapsedMilliseconds;
                if (options.Progress != null && (ms - Interlocked.Read(ref lastProgressMs) >= 250 || n == total))
                {
                    Interlocked.Exchange(ref lastProgressMs, ms);
                    options.Progress.Report(new SimProgress(n, total, clock.Elapsed));
                }

                if (options.OutPath != null && (n - Volatile.Read(ref lastCheckpointDone) >= cfg.Output.CheckpointEveryGames
                    || (clock.ElapsedTicks - Interlocked.Read(ref lastCheckpointTicks)) / (double)Stopwatch.Frequency >= cfg.Output.CheckpointEverySeconds))
                {
                    if (Monitor.TryEnter(gate))
                    {
                        try
                        {
                            Write(Build(cfg, records, started, "running", total), options.OutPath);
                            Volatile.Write(ref lastCheckpointDone, n);
                            Interlocked.Exchange(ref lastCheckpointTicks, clock.ElapsedTicks);
                        }
                        finally { Monitor.Exit(gate); }
                    }
                }
            });
        }
        catch (OperationCanceledException)
        {
            cancelled = true;
        }

        var result = Build(cfg, records, started, cancelled ? "cancelled" : "completed", total);
        result.FinishedUtc = DateTime.UtcNow;
        if (options.OutPath != null) Write(result, options.OutPath);
        return result;
    }

    private static SimulationResult Build(SimulationConfig cfg, GameRecord?[] records, DateTime started, string status, int total)
    {
        var list = new List<GameRecord>(records.Length);
        foreach (var r in records) if (r != null) list.Add(r); // index order, independent of thread timing
        var result = new SimulationResult
        {
            Status = status,
            StartedUtc = started,
            GamesRequested = total,
            Config = cfg,
        };
        ResultSummarizer.Fill(result, list);
        if (cfg.Output.PerGameRecords) result.Games = list;
        return result;
    }

    /// <summary>Write to a temp file then move it over the target, so a crash never leaves a half-written result.</summary>
    public static void Write(SimulationResult result, string path)
    {
        string? dir = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        string tmp = path + ".tmp";
        using (var fs = File.Create(tmp))
            JsonSerializer.Serialize(fs, result, SimulationConfig.JsonOptions);
        File.Move(tmp, path, overwrite: true);
    }

    public static SimulationResult LoadForResume(string path)
    {
        var r = JsonSerializer.Deserialize<SimulationResult>(File.ReadAllText(path), SimulationConfig.JsonOptions)
                ?? throw new InvalidDataException($"Empty result file: {path}");
        if (r.Games.Count == 0 && r.GamesCompleted > 0)
            throw new InvalidDataException("Cannot resume: the file has no per-game records (output.perGameRecords was false).");
        return r;
    }

    private static void EnsureCompatible(SimulationConfig now, SimulationConfig before)
    {
        string Key(SimulationConfig c) => JsonSerializer.Serialize(new { c.Players, c.Seed, c.SeatOrder, c.Seats, c.Limits, c.Options.AutoAdvanceForced }, SimulationConfig.JsonOptions);
        if (Key(now) != Key(before))
            throw new InvalidDataException("The result file was produced with a different config (seed, seats, order or limits); cannot resume.");
    }
}
