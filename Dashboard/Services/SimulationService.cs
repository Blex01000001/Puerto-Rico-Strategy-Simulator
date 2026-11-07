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

    public event Action? Changed;

    public async Task StartAsync(SimulationConfig cfg, string fileName)
    {
        if (Running) return;
        Error = null; Progress = null; LastOutput = null;
        try { cfg.Validate(); }
        catch (InvalidDataException e) { Error = e.Message; Changed?.Invoke(); return; }

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
            Error = $"模擬失敗：{e.Message}";
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
}
