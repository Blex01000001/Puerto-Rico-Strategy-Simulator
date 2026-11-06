using System.Text.Json;
using PuertoRico.Engine.Simulation;
using Xunit;

namespace PuertoRico.Tests;

public class SweepTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "pr-sweep-" + Guid.NewGuid().ToString("N"));
    public SweepTests() => Directory.CreateDirectory(_dir);
    public void Dispose() => Directory.Delete(_dir, true);

    private static SimulationConfig Cfg(params (string name, double[] values)[] grid)
    {
        var cfg = new SimulationConfig
        {
            Games = 150,
            Seed = 12,
            Seats = new List<SeatConfig>
            {
                new() { Id = "h", Strategy = "harbor-rush" },
                new() { Id = "c", Strategy = "corn-shipper" },
                new() { Id = "r", Strategy = "random" },
            },
            Sweep = new SweepConfig { Target = "h" },
        };
        foreach (var (name, values) in grid) cfg.Sweep.Parameters[name] = values.ToList();
        return cfg;
    }

    [Fact]
    public void Grid_Is_The_Cartesian_Product_In_A_Fixed_Order()
    {
        var sweep = Cfg(("b", new[] { 1.0, 2 }), ("a", new[] { 10.0, 20, 30 })).Sweep!;
        var grid = SweepRunner.Grid(sweep);
        Assert.Equal(6, grid.Count);
        Assert.Equal(new[] { "a", "b" }, grid[0].Keys.OrderBy(k => k));
        Assert.Equal(10, grid[0]["a"]); Assert.Equal(1, grid[0]["b"]);
        Assert.Equal(10, grid[1]["a"]); Assert.Equal(2, grid[1]["b"]);
        Assert.Equal(30, grid[5]["a"]); Assert.Equal(2, grid[5]["b"]);
    }

    [Fact]
    public void Runs_Every_Point_Applies_The_Parameters_And_Is_Reproducible()
    {
        var cfg = Cfg(("quarryTarget", new[] { 0.0, 3 }), ("buildThreshold", new[] { 5.0, 7 }));
        var a = SweepRunner.Run(cfg, null, null, CancellationToken.None);
        var b = SweepRunner.Run(cfg, null, null, CancellationToken.None);
        Assert.Equal("completed", a.Status);
        Assert.Equal(4, a.Points.Count);
        Assert.All(a.Points, p => Assert.Equal(150, p.Games));
        Assert.All(a.Points, p => Assert.Equal(3, p.Seats.Count));
        string J(object o) => JsonSerializer.Serialize(o, SimulationConfig.JsonOptions);
        Assert.Equal(J(a.Points), J(b.Points));
        Assert.True(a.Points.Select(p => p.WinShare).Distinct().Count() > 1, "parameters must change the outcome");
        Assert.Equal(a.Points.Max(p => p.WinShare), a.Points[a.BestIndex].WinShare);
        Assert.All(a.Points, p => Assert.InRange(p.WinShareCi95, 0.0, 0.2));
    }

    [Fact]
    public void Does_Not_Modify_The_Callers_Config_And_Writes_The_File()
    {
        var cfg = Cfg(("quarryTarget", new[] { 0.0, 1 }));
        string path = Path.Combine(_dir, "s.json");
        SweepRunner.Run(cfg, path, null, CancellationToken.None);
        Assert.Empty(cfg.Seats[0].Params);
        var disk = JsonSerializer.Deserialize<SweepResult>(File.ReadAllText(path), SimulationConfig.JsonOptions)!;
        Assert.Equal("completed", disk.Status);
        Assert.Equal(2, disk.Points.Count);
        Assert.False(File.Exists(path + ".tmp"));
    }

    [Fact]
    public void Cancellation_Returns_The_Finished_Points_As_Cancelled()
    {
        var cfg = Cfg(("quarryTarget", new[] { 0.0, 1, 2 }));
        using var cts = new CancellationTokenSource();
        cts.Cancel();
        var r = SweepRunner.Run(cfg, null, null, cts.Token);
        Assert.Equal("cancelled", r.Status);
        Assert.True(r.Points.Count < 3);
    }

    [Fact]
    public void Validation_Rejects_Bad_Sweeps()
    {
        var noTarget = Cfg(("quarryTarget", new[] { 1.0 }));
        noTarget.Sweep!.Target = "zzz";
        Assert.Throws<InvalidDataException>(() => SweepRunner.Validate(noTarget));
        var empty = Cfg();
        Assert.Throws<InvalidDataException>(() => SweepRunner.Validate(empty));
        var none = Cfg(("x", new[] { 1.0 }));
        none.Sweep = null;
        Assert.Throws<InvalidDataException>(() => SweepRunner.Validate(none));
    }

    [Fact]
    public void Config_With_Sweep_Section_Loads_From_Json()
    {
        var cfg = SimulationConfig.Clone(Cfg(("quarryTarget", new[] { 0.0, 1 })));
        Assert.Equal("h", cfg.Sweep!.Target);
        Assert.Equal(new[] { 0.0, 1 }, cfg.Sweep.Parameters["quarryTarget"]);
    }
}
