using System.Text.Json;
using PuertoRico.Engine.Events;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies;

// Run: dotnet run -c Release --project tools/mctsdepth -- mcts/value/4p-v2-vs-default.json [games] [simulations]
//   games        default: the config's (trimmed to a multiple of 24 / 6 so balanced seats stay fair; the games are played in parallel)
//   simulations  overrides params.simulations of every MCTS seat (to compare 300 / 600 / 1200 on the same table and seed)
// For every decision an MCTS seat actually searched (forced single-action decisions are skipped) it reports, per game phase, how wide the
// tree is at the root and how deep the search got: legal actions, simulations per action, unvisited actions, depth of the most visited
// line below the chosen action (capped at 8 by the engine), visit share of the chosen action, and the traffic light of the chosen action
// against the 2nd most visited one (docs/strategy-analysis.md section 5, TODO 4 / 10(g)). Reads the engine only; nothing is written.
if (args.Length < 1) { Console.Error.WriteLine("usage: mctsdepth <config.json> [games] [simulations]"); return 1; }
var cfg = SimulationConfig.Load(args[0]);
int games = args.Length > 1 ? int.Parse(args[1]) : cfg.Games;
int unit = cfg.Players == 4 ? 24 : 6;
games -= games % unit;
if (games <= 0) { Console.Error.WriteLine($"games must be at least {unit} (balanced seats)"); return 1; }
if (args.Length > 2)
{
    int sims = int.Parse(args[2]);
    foreach (var s in cfg.Seats.Where(s => s.Strategy.Equals("mcts", StringComparison.OrdinalIgnoreCase)))
        s.Params["simulations"] = JsonSerializer.SerializeToElement(sims);
}
cfg.Games = games;
cfg.SeatOrder = SeatOrderMode.Balanced;

var total = new Dictionary<Phase, PhaseStat>();
var gate = new object();
var started = DateTime.UtcNow;
Parallel.For(0, games, i =>
{
    var sink = new Collect();
    GameRunner.Play(cfg, i, sink);
    lock (gate)
        foreach (var kv in sink.Stats)
        {
            if (!total.TryGetValue(kv.Key, out var t)) total[kv.Key] = t = new PhaseStat();
            t.Merge(kv.Value);
        }
});

var sims0 = total.Values.FirstOrDefault()?.SimulationsSeen ?? 0;
Console.WriteLine($"config {Path.GetFileName(args[0])}, {games} games, simulations {(sims0 == 0 ? "-" : sims0.ToString())}, took {(DateTime.UtcNow - started).TotalSeconds:0} s");
Console.WriteLine();
Console.WriteLine("| phase | searched decisions | share | avg legal actions | sims / action | unvisited actions | depth of main line | depth 8+ | top action share | green | yellow | red |");
Console.WriteLine("|---|---|---|---|---|---|---|---|---|---|---|---|");
var all = new PhaseStat();
foreach (var kv in total.OrderBy(k => k.Key)) all.Merge(kv.Value);
foreach (var kv in total.OrderBy(k => k.Key)) Row(kv.Key.ToString(), kv.Value, all.N);
Row("**all**", all, all.N);
Console.WriteLine();
Console.WriteLine("depth of main line = number of replies below the chosen action along the most visited path (0 = the chosen action was never expanded further); capped at 8 by the engine.");
Console.WriteLine("unvisited actions = share of the legal actions that got no simulation at all. green/yellow/red = the chosen action against the 2nd most visited one (SearchSummary.Assess).");
return 0;

static void Row(string name, PhaseStat s, long n)
{
    if (s.N == 0) return;
    double d = s.N;
    Console.WriteLine($"| {name} | {s.N:N0} | {100.0 * s.N / Math.Max(1, n):0.0} % | {s.Legal / d:0.0} | {s.SimsPerAction / d:0.0} | {100.0 * s.Unvisited / d:0.0} % | {s.Depth / d:0.00} | {100.0 * s.DepthCap / d:0.0} % | {100.0 * s.TopShare / d:0.0} % | {100.0 * s.Green / d:0.0} % | {100.0 * s.Yellow / d:0.0} % | {100.0 * s.Red / d:0.0} % |");
}

sealed class PhaseStat
{
    public long N, DepthCap, Green, Yellow, Red;
    public double Legal, SimsPerAction, Unvisited, Depth, TopShare;
    public int SimulationsSeen;

    public void Add(SearchSummary s)
    {
        N++;
        SimulationsSeen = s.Simulations;
        int legal = s.Actions.Count;
        Legal += legal;
        SimsPerAction += (double)s.Simulations / legal;
        Unvisited += (double)s.Actions.Count(a => a.Visits == 0) / legal;
        var ordered = s.Actions.OrderByDescending(a => a.Visits).ThenByDescending(a => a.MeanReward).ToList();
        var top = ordered[0];
        TopShare += (double)top.Visits / Math.Max(1, s.Actions.Sum(a => a.Visits));
        int depth = top.Line?.Count ?? 0;
        Depth += depth;
        if (depth >= 8) DepthCap++;
        switch (SearchSummary.Assess(top, ordered.Skip(1).Take(1).ToList()))
        {
            case SearchSummary.PickSignal.Green: Green++; break;
            case SearchSummary.PickSignal.Red: Red++; break;
            default: Yellow++; break;
        }
    }

    public void Merge(PhaseStat o)
    {
        N += o.N; DepthCap += o.DepthCap; Green += o.Green; Yellow += o.Yellow; Red += o.Red;
        Legal += o.Legal; SimsPerAction += o.SimsPerAction; Unvisited += o.Unvisited; Depth += o.Depth; TopShare += o.TopShare;
        if (o.SimulationsSeen != 0) SimulationsSeen = o.SimulationsSeen;
    }
}

sealed class Collect : IGameEventSink
{
    public Dictionary<Phase, PhaseStat> Stats { get; } = new();
    private SearchSummary? _search;
    public bool Enabled => true;
    public void OnSearch(SearchSummary search) => _search = search;
    public void OnDecision(GameState before, GameAction action)
    {
        if (_search != null)
        {
            if (!Stats.TryGetValue(before.Phase, out var ps)) Stats[before.Phase] = ps = new PhaseStat();
            ps.Add(_search);
        }
        _search = null;
    }
}
