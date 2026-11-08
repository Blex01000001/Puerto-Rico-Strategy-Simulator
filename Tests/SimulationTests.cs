using System.Text.Json;
using PuertoRico.Engine.Events;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using Xunit;

namespace PuertoRico.Tests;

public class FuzzTests
{
    [Fact]
    public void Random_Games_Keep_All_Invariants_And_Always_Terminate()
    {
        var rng = new Random(42);
        int ended = 0;
        var reasons = new HashSet<EndFlags>();
        for (int game = 0; game < 300; game++)
        {
            var s = Setup.NewGame((ulong)game + 1000);
            var legal = new List<GameAction>();
            int steps = 0;
            while (!s.IsOver)
            {
                Rules.GetLegalActions(s, legal);
                Assert.NotEmpty(legal);
                var a = legal[rng.Next(legal.Count)];
                Rules.Apply(s, a);
                var err = Invariants.Check(s);
                Assert.True(err == null, $"game {game} step {steps} after {a}: {err}");
                Assert.True(++steps < 20000, "game did not end");
            }
            ended++;
            reasons.Add(s.EndFlags);
            var score = Scoring.Score(s);
            Assert.NotEmpty(score.Winners);
        }
        Assert.Equal(300, ended);
        Assert.True(reasons.Count >= 2); // different end conditions show up
    }

    [Fact]
    public void Every_Legal_Action_Is_Accepted_By_The_Checked_Apply()
    {
        var s = Setup.NewGame(5);
        var rng = new Random(3);
        var legal = new List<GameAction>();
        for (int i = 0; i < 600 && !s.IsOver; i++)
        {
            Rules.GetLegalActions(s, legal);
            foreach (var a in legal) Rules.ApplyChecked(s.Clone(), a); // every listed action really works
            Rules.Apply(s, legal[rng.Next(legal.Count)]);
        }
    }
}

public class DeterminismTests
{
    private static SimulationConfig Cfg(int games = 200, int degree = 1) => new()
    {
        Games = games,
        Seed = 777,
        Parallelism = new ParallelismConfig { MaxDegree = degree },
    };

    private static string Json(object o) => JsonSerializer.Serialize(o, SimulationConfig.JsonOptions);

    [Fact]
    public void Same_Config_And_Index_Give_The_Same_Game()
    {
        var cfg = Cfg();
        Assert.Equal(Json(GameRunner.Play(cfg, 17)), Json(GameRunner.Play(cfg, 17)));
        Assert.NotEqual(Json(GameRunner.Play(cfg, 17)), Json(GameRunner.Play(cfg, 18)));
    }

    [Fact]
    public void Result_Does_Not_Depend_On_Thread_Count()
    {
        var one = BatchSimulator.Run(Cfg(300, 1), new BatchOptions(), CancellationToken.None);
        var many = BatchSimulator.Run(Cfg(300, 8), new BatchOptions(), CancellationToken.None);
        Assert.Equal(Json(one.Games), Json(many.Games));
        Assert.Equal(Json(one.Summary), Json(many.Summary));
        Assert.Equal("completed", many.Status);
    }

    [Fact]
    public void Different_Master_Seeds_Give_Different_Games()
    {
        var a = Cfg(); var b = Cfg(); b.Seed = 778;
        Assert.NotEqual(Json(GameRunner.Play(a, 0)), Json(GameRunner.Play(b, 0)));
    }

    [Fact]
    public void Rotate_Moves_Every_Strategy_Through_Every_Seat()
    {
        var cfg = Cfg(); cfg.SeatOrder = SeatOrderMode.Rotate;
        var seen = new Dictionary<string, HashSet<int>> { ["A"] = new(), ["B"] = new(), ["C"] = new() };
        for (int i = 0; i < 6; i++)
            foreach (var p in GameRunner.Play(cfg, i).Players) seen[p.SeatId].Add(p.Seat);
        Assert.All(seen.Values, v => Assert.Equal(3, v.Count));
    }

    [Fact]
    public void Default_Seat_Order_Is_Random_Also_When_The_File_Does_Not_Say()
    {
        Assert.Equal(SeatOrderMode.Random, new SimulationConfig().SeatOrder);
        var cfg = System.Text.Json.JsonSerializer.Deserialize<SimulationConfig>("{ \"games\": 3 }", SimulationConfig.JsonOptions)!;
        Assert.Equal(SeatOrderMode.Random, cfg.SeatOrder);
        var balanced = System.Text.Json.JsonSerializer.Deserialize<SimulationConfig>("{ \"seatOrder\": \"balanced\" }", SimulationConfig.JsonOptions)!;
        Assert.Equal(SeatOrderMode.Balanced, balanced.SeatOrder);
    }

    /// <summary>Balanced = every permutation of the seats the same number of times, so every strategy sits in every seat
    /// and next to every other strategy (on its left and on its right) equally often.</summary>
    [Theory]
    [InlineData(3, 6)]
    [InlineData(4, 24)]
    public void Balanced_Order_Plays_Every_Permutation_Equally_Often_And_Balances_Neighbours(int players, int perms)
    {
        const int Rounds = 3;
        var cfg = new SimulationConfig { Players = players, Seed = 1, SeatOrder = SeatOrderMode.Balanced };
        var permutations = new Dictionary<string, int>();
        var seatCount = new int[players, players];       // [strategy, table seat]
        var rightOf = new int[players, players];         // [strategy, strategy sitting at the next table seat]
        for (int g = 0; g < perms * Rounds; g++)
        {
            var map = GameRunner.SeatAssignment(cfg, g, SeedDeriver.GameSeed(cfg.Seed, g)); // table seat -> config seat
            Assert.Equal(Enumerable.Range(0, players), map.OrderBy(x => x));
            string key = string.Join(",", map);
            permutations[key] = permutations.GetValueOrDefault(key) + 1;
            for (int seat = 0; seat < players; seat++)
            {
                seatCount[map[seat], seat]++;
                rightOf[map[seat], map[(seat + 1) % players]]++;
            }
        }
        Assert.Equal(perms, permutations.Count);
        Assert.All(permutations.Values, c => Assert.Equal(Rounds, c));
        for (int a = 0; a < players; a++)
            for (int b = 0; b < players; b++)
            {
                Assert.Equal(perms * Rounds / players, seatCount[a, b]);
                if (a != b) Assert.Equal(perms * Rounds / (players - 1), rightOf[a, b]);
            }
    }

    [Fact]
    public void Fixed_Order_Never_Moves_Strategies_And_Random_Order_Is_A_Permutation()
    {
        var fixedCfg = Cfg(); fixedCfg.SeatOrder = SeatOrderMode.Fixed;
        for (int i = 0; i < 5; i++)
            Assert.Equal(new[] { "A", "B", "C" }, GameRunner.Play(fixedCfg, i).Players.OrderBy(p => p.Seat).Select(p => p.SeatId));
        var randCfg = Cfg(); randCfg.SeatOrder = SeatOrderMode.Random;
        for (int i = 0; i < 20; i++)
            Assert.Equal(new[] { "A", "B", "C" }, GameRunner.Play(randCfg, i).Players.Select(p => p.SeatId).OrderBy(x => x));
    }

    [Fact]
    public void Event_Log_Is_Only_Filled_When_A_Sink_Is_Given_And_Does_Not_Change_The_Game()
    {
        var cfg = Cfg();
        var sink = new ListEventSink();
        var withLog = GameRunner.Play(cfg, 3, sink);
        var without = GameRunner.Play(cfg, 3);
        Assert.NotEmpty(sink.Events);
        Assert.Equal(Json(withLog), Json(without));
        Assert.Equal(withLog.Decisions, sink.Events.Count);
    }

    [Fact]
    public void Decision_Limit_Ends_The_Game_And_Is_Reported()
    {
        var cfg = Cfg(); cfg.Limits.MaxDecisionsPerGame = 30;
        var rec = GameRunner.Play(cfg, 0);
        Assert.Contains("decisionLimit", rec.EndReason);
    }

    [Fact]
    public void Round_Limit_Is_Reported_In_The_Record()
    {
        var cfg = Cfg(); cfg.Limits.MaxRounds = 3;
        var rec = GameRunner.Play(cfg, 0);
        Assert.Equal("roundLimit", rec.EndReason);
        Assert.Equal(3, rec.Rounds);
    }
}

public class BatchTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "pr-tests-" + Guid.NewGuid().ToString("N"));
    public BatchTests() => Directory.CreateDirectory(_dir);
    public void Dispose() => Directory.Delete(_dir, true);

    private static SimulationConfig Cfg(int games) => new() { Games = games, Seed = 99 };
    private static string Json(object o) => JsonSerializer.Serialize(o, SimulationConfig.JsonOptions);

    [Fact]
    public void Resume_Gives_The_Same_Result_As_A_Straight_Run()
    {
        var straight = BatchSimulator.Run(Cfg(120), new BatchOptions(), CancellationToken.None);

        string path = Path.Combine(_dir, "r.json");
        BatchSimulator.Run(Cfg(50), new BatchOptions { OutPath = path }, CancellationToken.None);
        var partial = BatchSimulator.LoadForResume(path);
        Assert.Equal(50, partial.GamesCompleted);
        var resumed = BatchSimulator.Run(Cfg(120), new BatchOptions { OutPath = path, ResumeFrom = partial }, CancellationToken.None);

        Assert.Equal(120, resumed.GamesCompleted);
        Assert.Equal(Json(straight.Games), Json(resumed.Games));
    }

    [Fact]
    public void Resume_Refuses_A_Different_Config()
    {
        string path = Path.Combine(_dir, "r.json");
        BatchSimulator.Run(Cfg(10), new BatchOptions { OutPath = path }, CancellationToken.None);
        var other = Cfg(20); other.Seed = 100;
        Assert.Throws<InvalidDataException>(() =>
            BatchSimulator.Run(other, new BatchOptions { ResumeFrom = BatchSimulator.LoadForResume(path) }, CancellationToken.None));
    }

    [Fact]
    public void Cancellation_Writes_A_Partial_Result_Marked_Cancelled()
    {
        string path = Path.Combine(_dir, "c.json");
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        var r = BatchSimulator.Run(Cfg(1000), new BatchOptions { OutPath = path }, cts.Token);
        Assert.Equal("cancelled", r.Status);
        Assert.True(r.GamesCompleted < 1000);
        var onDisk = BatchSimulator.LoadForResume(path);
        Assert.Equal("cancelled", onDisk.Status);
    }

    [Fact]
    public void Checkpoints_Are_Written_During_The_Run_And_Final_File_Is_Complete()
    {
        string path = Path.Combine(_dir, "k.json");
        var cfg = Cfg(400);
        cfg.Output.CheckpointEveryGames = 20;
        var r = BatchSimulator.Run(cfg, new BatchOptions { OutPath = path }, CancellationToken.None);
        Assert.Equal("completed", r.Status);
        var disk = JsonSerializer.Deserialize<SimulationResult>(File.ReadAllText(path), SimulationConfig.JsonOptions)!;
        Assert.Equal("completed", disk.Status);
        Assert.Equal(400, disk.Games.Count);
        Assert.Equal(Enumerable.Range(0, 400), disk.Games.Select(g => g.Index));
        Assert.False(File.Exists(path + ".tmp"));
    }

    [Fact]
    public void Without_PerGameRecords_The_File_Has_Only_The_Summary()
    {
        var cfg = Cfg(40); cfg.Output.PerGameRecords = false;
        var r = BatchSimulator.Run(cfg, new BatchOptions(), CancellationToken.None);
        Assert.Empty(r.Games);
        Assert.Equal(40, r.GamesCompleted);
        Assert.Equal(3, r.Summary.Count);
        Assert.Equal(1.0, r.Summary.Sum(s => s.WinShare), 6);
    }

    [Fact]
    public void Config_Round_Trips_And_Validates()
    {
        var cfg = Cfg(5);
        cfg.Seats[1].Params["x"] = JsonDocument.Parse("1.5").RootElement.Clone();
        var back = JsonSerializer.Deserialize<SimulationConfig>(Json(cfg), SimulationConfig.JsonOptions)!;
        Assert.Equal(Json(cfg), Json(back));
        back.Validate();
        back.Seats[0].Strategy = "nope";
        Assert.Throws<InvalidDataException>(() => back.Validate());
    }

    [Fact]
    public void Config_File_Is_Read_With_CamelCase_And_Comments()
    {
        string path = Path.Combine(_dir, "cfg.json");
        File.WriteAllText(path, """
            { // comment
              "name": "t", "games": 7, "seed": 5, "seatOrder": "fixed",
              "seats": [ {"id":"X","strategy":"random"}, {"id":"Y","strategy":"random"}, {"id":"Z","strategy":"random"} ],
              "limits": { "maxRounds": 40 }
            }
            """);
        var cfg = SimulationConfig.Load(path);
        Assert.Equal(7, cfg.Games);
        Assert.Equal(SeatOrderMode.Fixed, cfg.SeatOrder);
        Assert.Equal(40, cfg.Limits.MaxRounds);
        Assert.Equal("Y", cfg.Seats[1].Id);
    }
}
