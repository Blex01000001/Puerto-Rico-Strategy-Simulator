using System.Text.Json;
using PuertoRico.Engine.Events;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;

namespace PuertoRico.Runner;

public static class Program
{
    private const string Usage = """
        PuertoRico Runner

        dotnet run -c Release --project Runner -- --config config.json --games 100000 --out result.json

          --config <file>      simulation config (JSON); default settings (3 random players) if omitted
          --games <n>          override config.games
          --seed <n>           override config.seed
          --threads <n>        override config.parallelism.maxDegree (0 = all cores)
          --out <file>         result file (default: result.json); checkpoints are written here too
          --resume             continue from an existing --out file of the same config
          --replay <index>     play one game with the event log on and write the events to --out
          --sweep              parameter sweep from config.sweep (see config.sweep.example.json); result in --out (default sweep.json)
          --help
        """;

    public static int Main(string[] args)
    {
        try
        {
            return Run(args);
        }
        catch (Exception e) when (e is ArgumentException or InvalidDataException or IOException or JsonException)
        {
            Console.Error.WriteLine($"error: {e.Message}");
            return 2;
        }
    }

    private static int Run(string[] args)
    {
        string? configPath = null, outPath = null;
        int? games = null, threads = null, replay = null;
        ulong? seed = null;
        bool resume = false, sweep = false;

        for (int i = 0; i < args.Length; i++)
        {
            string Next() => i + 1 < args.Length ? args[++i] : throw new ArgumentException($"{args[i]} needs a value");
            switch (args[i])
            {
                case "--config": configPath = Next(); break;
                case "--games": games = int.Parse(Next()); break;
                case "--seed": seed = ulong.Parse(Next()); break;
                case "--threads": threads = int.Parse(Next()); break;
                case "--out": outPath = Next(); break;
                case "--resume": resume = true; break;
                case "--replay": replay = int.Parse(Next()); break;
                case "--sweep": sweep = true; break;
                case "--help" or "-h": Console.WriteLine(Usage); return 0;
                default: throw new ArgumentException($"unknown argument '{args[i]}'\n\n{Usage}");
            }
        }

        var cfg = configPath != null ? SimulationConfig.Load(configPath) : new SimulationConfig();
        if (games != null) cfg.Games = games.Value;
        if (seed != null) cfg.Seed = seed.Value;
        if (threads != null) cfg.Parallelism.MaxDegree = threads.Value;
        cfg.Validate();
        outPath ??= Path.Combine(Directory.GetCurrentDirectory(), replay != null ? "replay.json" : sweep ? "sweep.json" : "result.json");

        if (replay != null) return Replay(cfg, replay.Value, outPath);
        if (sweep) return Sweep(cfg, outPath);

        var options = new BatchOptions { OutPath = outPath };
        if (resume)
        {
            if (!File.Exists(outPath)) throw new ArgumentException($"--resume: '{outPath}' does not exist");
            options.ResumeFrom = BatchSimulator.LoadForResume(outPath);
            Console.Error.WriteLine($"resuming: {options.ResumeFrom.GamesCompleted} games already done");
        }
        options.Progress = new Progress<SimProgress>(p =>
            Console.Error.Write($"\r{p.Completed}/{p.Total} games ({100.0 * p.Completed / Math.Max(1, p.Total):F1}%)  {p.GamesPerSecond:F0} games/s   "));

        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true; // finish cleanly: write what we have, then exit
            Console.Error.WriteLine("\ncancelling, writing partial result...");
            cts.Cancel();
        };

        var result = BatchSimulator.Run(cfg, options, cts.Token);
        Console.Error.WriteLine();
        Console.WriteLine($"{result.Status}: {result.GamesCompleted}/{result.GamesRequested} games -> {outPath}");
        foreach (var s in result.Summary)
            Console.WriteLine($"  {s.SeatId} ({s.Strategy}): win share {s.WinShare:P1}, avg score {s.AvgScore:F1} ± {s.StdScore:F1}");
        return result.Status == "completed" ? 0 : 130;
    }

    private static int Sweep(SimulationConfig cfg, string outPath)
    {
        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true;
            Console.Error.WriteLine("\ncancelling after the current point...");
            cts.Cancel();
        };
        var log = new Progress<string>(m => Console.Error.WriteLine(m));
        var result = SweepRunner.Run(cfg, outPath, log, cts.Token);
        Console.WriteLine($"{result.Status}: {result.Points.Count}/{result.PointsPlanned} points -> {outPath}");
        foreach (var p in result.Points.OrderByDescending(p => p.WinShare))
            Console.WriteLine($"  {p.WinShare,6:P1} ± {p.WinShareCi95:P1}  avg {p.AvgScore,5:F1}  {SweepRunner.Describe(p.Params)}");
        return result.Status == "completed" ? 0 : 130;
    }

    private static int Replay(SimulationConfig cfg, int index, string outPath)
    {
        var sink = new ListEventSink();
        var record = GameRunner.Play(cfg, index, sink);
        var doc = new { record, events = sink.Events };
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outPath))!);
        File.WriteAllText(outPath, JsonSerializer.Serialize(doc, SimulationConfig.JsonOptions));
        Console.WriteLine($"game {index}: {record.EndReason}, {record.Rounds} rounds, {sink.Events.Count} decisions -> {outPath}");
        return 0;
    }
}
