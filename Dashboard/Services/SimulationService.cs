using PuertoRico.Engine.Simulation;

namespace Dashboard.Services;

/// <summary>Runs one batch simulation in the background of the Dashboard process (per browser session).</summary>
public sealed class SimulationService : IDisposable
{
    private readonly AppState _state;
    private readonly IConfiguration _config;
    private CancellationTokenSource? _cts;

    public SimulationService(AppState state, IConfiguration config) { _state = state; _config = config; }

    public bool Running { get; private set; }
    public SimProgress? Progress { get; private set; }
    public string? Error { get; private set; }
    public string? LastOutput { get; private set; }
    /// <summary>True when the last/current job is a parameter sweep.</summary>
    public bool IsSweep { get; private set; }
    public int SweepDone { get; private set; }
    public int SweepTotal { get; private set; }
    public string? SweepLog { get; private set; }

    public event Action? Changed;

    public async Task StartAsync(SimulationConfig cfg, string fileName)
    {
        if (Running) return;
        Error = null; Progress = null; LastOutput = null; IsSweep = false;
        try { cfg.Validate(); }
        catch (InvalidDataException e) { Error = AppState.Scrub(e.Message); Changed?.Invoke(); return; }

        string dir = AppState.ResultsDirectory(_config);
        string path = Path.Combine(dir, fileName);
        _cts = new CancellationTokenSource();
        var ct = _cts.Token;
        Running = true; Changed?.Invoke();
        try
        {
            var options = new BatchOptions { OutPath = path, Progress = new Reporter(this) };
            var result = await Task.Run(() => BatchSimulator.Run(cfg, options, ct));
            LastOutput = path;
            Running = false;
            if (result.GamesCompleted > 0) await _state.LoadPathAsync(path);
        }
        catch (Exception e)
        {
            Error = $"模擬失敗：{AppState.Scrub(e.Message)}";
        }
        finally
        {
            Running = false;
            Changed?.Invoke();
        }
    }

    public async Task StartSweepAsync(SimulationConfig cfg, string fileName)
    {
        if (Running) return;
        Error = null; Progress = null; LastOutput = null; IsSweep = true; SweepDone = 0; SweepLog = null;
        try
        {
            SweepRunner.Validate(cfg);
            SweepTotal = SweepRunner.Grid(cfg.Sweep!).Count;
        }
        catch (InvalidDataException e) { Error = AppState.Scrub(e.Message); Changed?.Invoke(); return; }

        string path = Path.Combine(AppState.ResultsDirectory(_config), fileName);
        _cts = new CancellationTokenSource();
        var ct = _cts.Token;
        Running = true; Changed?.Invoke();
        try
        {
            var log = new SweepReporter(this);
            var result = await Task.Run(() => SweepRunner.Run(cfg, path, log, ct));
            LastOutput = path;
            Running = false;
            if (result.Points.Count > 0) await _state.LoadPathAsync(path);
        }
        catch (Exception e)
        {
            Error = $"掃描失敗：{AppState.Scrub(e.Message)}";
        }
        finally
        {
            Running = false;
            Changed?.Invoke();
        }
    }

    public void Cancel() => _cts?.Cancel();

    public void Dispose() { _cts?.Cancel(); _cts?.Dispose(); }

    private sealed class Reporter : IProgress<SimProgress>
    {
        private readonly SimulationService _owner;
        public Reporter(SimulationService owner) => _owner = owner;
        public void Report(SimProgress value) { _owner.Progress = value; _owner.Changed?.Invoke(); }
    }

    private sealed class SweepReporter : IProgress<string>
    {
        private readonly SimulationService _owner;
        public SweepReporter(SimulationService owner) => _owner = owner;
        public void Report(string value)
        {
            _owner.SweepDone++;
            _owner.SweepLog = value;
            _owner.Changed?.Invoke();
        }
    }
}
