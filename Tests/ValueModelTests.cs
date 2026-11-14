using System.Globalization;
using System.Text.Json;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies.Mcts;
using Xunit;

namespace PuertoRico.Tests;

public class ValueModelTests
{
    private static string DataPath(string file) => Path.Combine(AppContext.BaseDirectory, "Data", file);

    [Fact]
    public void LightGbm_text_model_reproduces_python_predictions()
    {
        // Tests/Data/tiny-lgbm.txt: 6 trees trained by lightgbm 4.7 on a 4p dump; the check file holds python's prediction + the features
        var model = LightGbmValueModel.Parse(File.ReadAllLines(DataPath("tiny-lgbm.txt")));
        int rows = 0;
        foreach (var line in File.ReadAllLines(DataPath("tiny-lgbm.check.txt")))
        {
            var v = line.Split(' ').Select(x => double.Parse(x, CultureInfo.InvariantCulture)).ToArray();
            var x = v.Skip(1).Select(d => (float)d).ToArray();
            Assert.Equal(ValueFeatures.Count, x.Length);
            Assert.Equal(v[0], model.Predict(x), 6);
            rows++;
        }
        Assert.True(rows >= 20);
    }

    [Fact]
    public void Model_with_other_feature_names_is_refused()
    {
        var lines = File.ReadAllLines(DataPath("tiny-lgbm.txt"))
            .Select(l => l.StartsWith("feature_names=") ? l.Replace(" round ", " roundX ") : l).ToArray();
        var e = Assert.Throws<InvalidDataException>(() => LightGbmValueModel.Parse(lines));
        Assert.Contains("retrain", e.Message);
    }

    [Fact]
    public void Mlp_json_model_applies_standardisation_relu_and_sigmoid()
    {
        int f = ValueFeatures.Count;
        int round = Array.IndexOf(ValueFeatures.Names, "round");
        var w1 = new float[2][];
        w1[0] = new float[f]; w1[0][round] = 1f;   // relu((round - 1) / 2)
        w1[1] = new float[f]; w1[1][round] = -1f;  // relu(-(round - 1) / 2) = 0 for round >= 1
        var json = JsonSerializer.Serialize(new
        {
            format = "mlp",
            features = ValueFeatures.Names,
            mean = Enumerable.Repeat(1f, f).ToArray(),
            scale = Enumerable.Repeat(2f, f).ToArray(),
            activation = "relu",
            output = "sigmoid",
            layers = new object[]
            {
                new { weights = w1, bias = new[] { 0f, 0f } },
                new { weights = new[] { new[] { 0.5f, 3f } }, bias = new[] { -1f } },
            },
        });
        var model = MlpValueModel.Parse(json);
        var x = new float[f];
        x[round] = 5; // hidden = (2, 0) -> 0.5 * 2 - 1 = 0 -> sigmoid 0.5
        Assert.Equal(0.5, model.Predict(x), 6);
        x[round] = 9; // hidden = (4, 0) -> 1 -> sigmoid(1)
        Assert.Equal(1 / (1 + Math.Exp(-1)), model.Predict(x), 6);
    }

    [Fact]
    public void Features_put_the_viewing_seat_first()
    {
        var s = Setup.NewGame(7, 150, 4);
        s.Coins[2] = 17;
        s.VpChips[3] = 9;
        int coins0 = Array.IndexOf(ValueFeatures.Names, "p0_coins");
        int coins3 = Array.IndexOf(ValueFeatures.Names, "p3_coins");
        int vp1 = Array.IndexOf(ValueFeatures.Names, "p1_vpChips");
        int actor0 = Array.IndexOf(ValueFeatures.Names, "actorRel0");
        int players = Array.IndexOf(ValueFeatures.Names, "players");
        var f2 = ValueFeatures.Extract(s, 2);
        Assert.Equal(17, f2[coins0]);
        Assert.Equal(9, f2[vp1]);           // seat 3 is the next seat after 2
        Assert.Equal(4, f2[players]);
        var f3 = ValueFeatures.Extract(s, 3);
        Assert.Equal(17, f3[coins3]);       // seat 2 is three seats after 3
        Assert.Equal(s.Actor == 3 ? 1 : 0, f3[actor0]);

        var three = Setup.NewGame(7, 150, 3);
        int present3 = Array.IndexOf(ValueFeatures.Names, "p3_present");
        Assert.Equal(0, ValueFeatures.Extract(three, 0)[present3]); // 3-player games leave the 4th block empty
        Assert.All(ValueFeatures.Extract(three, 1), v => Assert.True(v >= short.MinValue && v <= short.MaxValue && v == Math.Floor(v)));
    }

    private static SimulationConfig MctsValueConfig(string model, int leafRollout)
    {
        var cfg = new SimulationConfig { Name = "value", Players = 4, Games = 2, Seed = 5, Seats = new List<SeatConfig>() };
        var m = new SeatConfig { Id = "m", Strategy = "mcts" };
        m.Params["simulations"] = JsonSerializer.SerializeToElement(20);
        m.Params["valueModel"] = JsonSerializer.SerializeToElement(model);
        m.Params["leafRollout"] = JsonSerializer.SerializeToElement(leafRollout);
        cfg.Seats.Add(m);
        for (int i = 1; i < 4; i++) cfg.Seats.Add(new SeatConfig { Id = $"c{i}", Strategy = "cheap-engine" });
        return cfg;
    }

    [Fact]
    public void Mcts_with_a_value_model_finishes_games_reproducibly()
    {
        foreach (int leaf in new[] { 0, 5 })
        {
            var cfg = MctsValueConfig(DataPath("tiny-lgbm.txt"), leaf);
            var a = GameRunner.Play(cfg, 0);
            var b = GameRunner.Play(cfg, 0);
            Assert.Equal(JsonSerializer.Serialize(a), JsonSerializer.Serialize(b));
            Assert.NotEmpty(a.Winners);
        }
    }

    [Fact]
    public void Missing_value_model_file_is_an_argument_error()
    {
        var cfg = MctsValueConfig(DataPath("does-not-exist.txt"), 0);
        Assert.Throws<ArgumentException>(() => GameRunner.Play(cfg, 0));
    }

    [Fact]
    public void Position_dump_is_independent_of_the_thread_count()
    {
        var dir = Path.Combine(Path.GetTempPath(), "pr-dump-" + Guid.NewGuid().ToString("N"));
        try
        {
            var cfg = new SimulationConfig { Name = "dump", Players = 3, Games = 70, Seed = 11 };
            cfg.Parallelism.MaxDegree = 1;
            var a = PositionDump.Run(cfg, Path.Combine(dir, "a.bin"), 0.05);
            cfg.Parallelism.MaxDegree = 4;
            var b = PositionDump.Run(cfg, Path.Combine(dir, "b.bin"), 0.05);
            Assert.Equal(a, b);
            Assert.True(a.Rows > 0);
            Assert.Equal(3 * a.Positions, a.Rows);
            var bytesA = File.ReadAllBytes(Path.Combine(dir, "a.bin"));
            Assert.Equal(a.Rows * PositionDump.RecordBytes, bytesA.Length);
            Assert.Equal(bytesA, File.ReadAllBytes(Path.Combine(dir, "b.bin")));
            using var meta = JsonDocument.Parse(File.ReadAllText(Path.Combine(dir, "a.bin.json")));
            Assert.Equal(ValueFeatures.Count, meta.RootElement.GetProperty("featureCount").GetInt32());
            // rewards of one position sum to 0.6 + 0.4 * (sum of rank scores) for a 3-player game without ties: 0.6 + 0.4 * 1.5 = 1.2
            float r0 = BitConverter.ToSingle(bytesA, 0), r1 = BitConverter.ToSingle(bytesA, PositionDump.RecordBytes), r2 = BitConverter.ToSingle(bytesA, 2 * PositionDump.RecordBytes);
            Assert.InRange(r0 + r1 + r2, 1.1, 1.3);
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }
}

public class PositionDumpCancelTests
{
    private sealed class CancelAfterFirst : IProgress<int>
    {
        private readonly CancellationTokenSource _cts;
        public CancelAfterFirst(CancellationTokenSource cts) => _cts = cts;
        public void Report(int value) => _cts.Cancel();
    }

    [Fact]
    public void Cancelled_dump_keeps_the_finished_chunk_and_writes_metadata()
    {
        var dir = Path.Combine(Path.GetTempPath(), "pr-dump-" + Guid.NewGuid().ToString("N"));
        try
        {
            var cfg = new SimulationConfig { Name = "dump", Players = 3, Games = 500, Seed = 3 };
            using var cts = new CancellationTokenSource();
            string path = Path.Combine(dir, "c.bin");
            var r = PositionDump.Run(cfg, path, 0.05, new CancelAfterFirst(cts), cts.Token);
            Assert.True(r.Cancelled);
            Assert.True(r.Games > 0 && r.Games < 500);
            Assert.Equal(r.Rows * PositionDump.RecordBytes, new FileInfo(path).Length);
            using var meta = JsonDocument.Parse(File.ReadAllText(path + ".json"));
            Assert.Equal("cancelled", meta.RootElement.GetProperty("status").GetString());
            Assert.Equal(r.Games, meta.RootElement.GetProperty("games").GetInt32());
            Assert.Equal(r.Rows, meta.RootElement.GetProperty("rows").GetInt64());
        }
        finally
        {
            if (Directory.Exists(dir)) Directory.Delete(dir, true);
        }
    }
}

public class ValueModelPathTests
{
    [Fact]
    public void Relative_model_path_is_found_from_a_project_subfolder()
    {
        // Visual Studio F5 starts the Dashboard inside Dashboard/: "ml/models/x.txt" must still resolve against the root
        var root = Path.Combine(Path.GetTempPath(), "pr-root-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(Path.Combine(root, "ml", "models"));
            Directory.CreateDirectory(Path.Combine(root, "Dashboard", "bin", "Release"));
            string model = Path.Combine(root, "ml", "models", "x.txt");
            File.WriteAllText(model, "");
            string rel = Path.Combine("ml", "models", "x.txt");
            Assert.Equal(model, ValueModels.Resolve(rel, root, root));                                           // from the root
            Assert.Equal(model, ValueModels.Resolve(rel, Path.Combine(root, "Dashboard"), "/elsewhere"));        // VS F5
            Assert.Equal(model, ValueModels.Resolve(rel, "/elsewhere", Path.Combine(root, "Dashboard", "bin", "Release"))); // program folder
            Assert.Equal(model, ValueModels.Resolve(model, "/elsewhere", "/elsewhere"));                         // absolute
            string missing = Path.Combine("ml", "models", "nope.txt");
            Assert.Equal(Path.GetFullPath(Path.Combine(root, missing)), ValueModels.Resolve(missing, root, root)); // not found: unchanged
        }
        finally
        {
            Directory.Delete(root, true);
        }
    }
}
