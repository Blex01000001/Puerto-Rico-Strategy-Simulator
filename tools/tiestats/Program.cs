using PuertoRico.Engine.Events;
// Run: dotnet run -c Release --project tools/tiestats -- 960 777 [cheap-engine,corn-shipper]   (games per table, seed, optional strategies whose tied sets are listed)
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies;

// Counts, for the hand-written strategies, how many scored decisions end in an exact tie at the top score (docs/strategy-analysis.md section 8).
int gamesPerTable = int.Parse(args.Length > 0 ? args[0] : "500");
var tables = new (int Players, string[] Seats)[]
{
    (4, new[] { "corn-shipper", "corn-to-premium", "harbor-rush", "build-first" }),
    (4, new[] { "cheap-engine", "wharf-rush", "wharf-premium", "corn-shipper" }),
    (4, new[] { "corn-monopoly", "corn-monopoly-tiles", "corn-monopoly-hoard", "harbor-rush" }),
    (3, new[] { "corn-shipper", "corn-to-premium", "harbor-rush" }),
    (3, new[] { "build-first", "cheap-engine", "wharf-rush" }),
    (3, new[] { "wharf-premium", "corn-monopoly", "build-first" }),
};

var perStrategy = new Dictionary<string, Stat>();
int games = 0; long decisions = 0;
foreach (var (players, seats) in tables)
{
    var cfg = new SimulationConfig { Name = "ties", Players = players, Games = gamesPerTable, Seed = ulong.Parse(args.Length > 1 ? args[1] : "2026"), SeatOrder = SeatOrderMode.Balanced,
        Seats = seats.Select(s => new SeatConfig { Id = s, Strategy = s }).ToList() };
    int g = gamesPerTable - gamesPerTable % (players == 4 ? 24 : 6);
    for (int i = 0; i < g; i++)
    {
        var sink = new Collect();
        var rec = GameRunner.Play(cfg, i, sink, out _);
        games++; decisions += rec.Decisions;
        foreach (var d in sink.Items)
        {
            string strat = rec.Players.First(p => p.Seat == d.Seat).SeatId;
            if (!perStrategy.TryGetValue(strat, out var st)) perStrategy[strat] = st = new Stat();
            st.Add(d);
        }
    }
}

if (args.Length > 2)
    foreach (var name in args[2].Split(','))
    {
        if (!perStrategy.TryGetValue(name, out var st)) continue;
        Console.WriteLine($"Most common tied sets of {name} (Mayor excluded):");
        foreach (var kv in st.Sets.OrderByDescending(k => k.Value).Take(25)) Console.WriteLine($"  {kv.Value,7:N0}  {kv.Key}");
    }
Console.WriteLine($"games {games}, total decisions (incl. forced, other seats) {decisions}");
Console.WriteLine();
Console.WriteLine("| strategy | scored decisions | top tie | tie % | avg tied | tie of different action kinds | Mayor decisions |");
Console.WriteLine("|---|---|---|---|---|---|---|");
var all = new Stat();
foreach (var kv in perStrategy.OrderBy(k => k.Key))
{
    var s = kv.Value; all.Merge(s);
    Console.WriteLine($"| {kv.Key} | {s.Scored:N0} | {s.Tied:N0} | {100.0 * s.Tied / Math.Max(1, s.Scored):0.0} % | {(s.Tied == 0 ? 0 : (double)s.TiedSizeSum / s.Tied):0.00} | {100.0 * s.TiedMixed / Math.Max(1, s.Tied):0.0} % | {s.Mayor:N0} |");
}
Console.WriteLine($"| **all** | {all.Scored:N0} | {all.Tied:N0} | {100.0 * all.Tied / Math.Max(1, all.Scored):0.0} % | {(double)all.TiedSizeSum / Math.Max(1, all.Tied):0.00} | {100.0 * all.TiedMixed / Math.Max(1, all.Tied):0.0} % | {all.Mayor:N0} |");
Console.WriteLine();
Console.WriteLine("By phase (all strategies, Mayor excluded):");
Console.WriteLine("| phase | scored decisions | top tie | tie % | avg tied |");
Console.WriteLine("|---|---|---|---|---|");
foreach (var kv in all.ByPhase.OrderBy(k => k.Key.ToString()))
    Console.WriteLine($"| {kv.Key} | {kv.Value.Scored:N0} | {kv.Value.Tied:N0} | {100.0 * kv.Value.Tied / Math.Max(1, kv.Value.Scored):0.0} % | {(kv.Value.Tied == 0 ? 0 : (double)kv.Value.TiedSizeSum / kv.Value.Tied):0.00} |");
Console.WriteLine();
Console.WriteLine("Tie % by strategy and phase (Mayor excluded):");
var phases = new[] { Phase.ChooseRole, Phase.Settler, Phase.Builder, Phase.CraftsmanBonus, Phase.Captain };
Console.WriteLine("| strategy | " + string.Join(" | ", phases) + " |");
Console.WriteLine("|---|" + string.Concat(phases.Select(_ => "---|")));
foreach (var kv in perStrategy.OrderBy(k => k.Key))
    Console.WriteLine($"| {kv.Key} | " + string.Join(" | ", phases.Select(ph => kv.Value.ByPhase.TryGetValue(ph, out var x) && x.Scored > 0 ? $"{100.0 * x.Tied / x.Scored:0.0} %" : "-")) + " |");
Console.WriteLine();
Console.WriteLine("What the tied actions are (kinds of the tied set), top 12:");
foreach (var kv in all.Kinds.OrderByDescending(k => k.Value).Take(12)) Console.WriteLine($"  {kv.Key}: {kv.Value:N0}");
Console.WriteLine();
Console.WriteLine($"Ties where the chosen action is not the lowest-index of the tied set (tie-break matters for a different pick): n/a (the chosen one is always first by construction)");

record Item(int Seat, Phase Phase, IReadOnlyList<ScoredAction> Scores, GameAction Action);

sealed class Collect : IGameEventSink
{
    public List<Item> Items { get; } = new();
    private IReadOnlyList<ScoredAction>? _scores;
    public bool Enabled => true;
    public void OnScores(IReadOnlyList<ScoredAction> scores) => _scores = scores;
    public void OnDecision(GameState before, GameAction action)
    {
        if (_scores != null) Items.Add(new Item(before.Actor, before.Phase, _scores, action));
        _scores = null;
    }
}

sealed class PhaseStat { public long Scored, Tied, TiedSizeSum; }

sealed class Stat
{
    public long Scored, Tied, TiedSizeSum, TiedMixed, Mayor;
    public Dictionary<Phase, PhaseStat> ByPhase = new();
    public Dictionary<string, long> Kinds = new();
    public Dictionary<string, long> Sets = new();

    public void Add(Item d)
    {
        if (d.Phase == Phase.Mayor) { Mayor++; return; }   // Mayor scores are circle values, the set is chosen as a whole
        Scored++;
        if (!ByPhase.TryGetValue(d.Phase, out var ps)) ByPhase[d.Phase] = ps = new PhaseStat();
        ps.Scored++;
        double max = d.Scores.Max(x => x.Score);
        var top = d.Scores.Where(x => x.Score == max).ToList();
        if (top.Count < 2) return;
        Tied++; TiedSizeSum += top.Count; ps.Tied++; ps.TiedSizeSum += top.Count;
        var kinds = top.Select(x => x.Action.Type).Distinct().ToList();
        if (kinds.Count > 1) TiedMixed++;
        string key = string.Join("+", kinds.OrderBy(k => k.ToString())) + $" (x{top.Count})";
        Kinds[key] = Kinds.GetValueOrDefault(key) + 1;
        string set = d.Phase + ": " + string.Join(" | ", top.Select(x => x.Action.ToString()).OrderBy(x => x, StringComparer.Ordinal));
        Sets[set] = Sets.GetValueOrDefault(set) + 1;
    }

    public void Merge(Stat o)
    {
        Scored += o.Scored; Tied += o.Tied; TiedSizeSum += o.TiedSizeSum; TiedMixed += o.TiedMixed; Mayor += o.Mayor;
        foreach (var kv in o.ByPhase) { if (!ByPhase.TryGetValue(kv.Key, out var p)) ByPhase[kv.Key] = p = new PhaseStat(); p.Scored += kv.Value.Scored; p.Tied += kv.Value.Tied; p.TiedSizeSum += kv.Value.TiedSizeSum; }
        foreach (var kv in o.Kinds) Kinds[kv.Key] = Kinds.GetValueOrDefault(kv.Key) + kv.Value;
    }
}
