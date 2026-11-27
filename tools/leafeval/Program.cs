using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies;
using PuertoRico.Engine.Strategies.Mcts;

// Run: dotnet run -c Release --project tools/leafeval -- ml/data-configs/4p-hand-a.json ml/models/4p-v2.txt [roots=400] [K=40] [S=40] [N=0,10,20,40,80,160] [seed=4242]
// Does leafRollout make the value model pick better actions? (docs/strategy-analysis.md 10.10, TODO 8)
// Takes positions ("roots") from games of a hand-written table where the actor has at least 2 legal actions (up to 8 actions are looked at).
// For every action a of a root, s_a is the position after a, and
//   truth(a) = average reward of the actor over K continuations of s_a played by the table's hand-written strategies (different draws)
//   est_N(a) = average over S samples of: play N random decisions from s_a (every seat picks uniformly among the legal actions, like the
//              MCTS rollout), then the model's value of the actor (the real game's score when the game ends first). N = 0 is "model on the leaf".
// For every N it reports how well the estimates order the actions: top-1 agreement with truth, regret (truth of the best action minus
// truth of the action est_N picks), the share of action pairs (truth differs by at least 0.03) ordered correctly, and the error of the
// leaf value itself (bias^2 of the average estimate, and the mean squared error of a single sample, which is what one simulation sees).
// Reference rows: a random pick (top-1 = 1 / actions, regret = best - average).
if (args.Length < 2) { Console.Error.WriteLine("usage: leafeval <config.json> <model> [roots] [K] [S] [N list] [seed]"); return 1; }
var cfg = SimulationConfig.Load(args[0]);
var model = ValueModels.Load(args[1]);
int rootsWanted = args.Length > 2 ? int.Parse(args[2]) : 400;
int K = args.Length > 3 ? int.Parse(args[3]) : 40;
int S = args.Length > 4 ? int.Parse(args[4]) : 40;
var Ns = (args.Length > 5 ? args[5] : "0,10,20,40,80,160").Split(',').Select(int.Parse).ToArray();
ulong seed = args.Length > 6 ? ulong.Parse(args[6]) : 4242;
int P = cfg.Players;
if (cfg.Seats.Any(s => s.Strategy.Equals("mcts", StringComparison.OrdinalIgnoreCase))) { Console.Error.WriteLine("use a hand-written table (no mcts seat)"); return 1; }
const int MaxActions = 8;
const double RootProbability = 0.012;

var groups = new Dictionary<string, Group[]>();
var gate = new object();
var started = DateTime.UtcNow;
int gamesNeeded = Math.Max(1, (int)Math.Ceiling(rootsWanted / 3.5));
Parallel.For(0, gamesNeeded, g =>
{
    ulong gameSeed = SeedDeriver.GameSeed(seed, g);
    int[] seatToConfig = GameRunner.SeatAssignment(cfg, g, gameSeed);
    var strategies = GameRunner.CreateStrategies(cfg, seatToConfig, gameSeed);
    var state = Setup.NewGame(gameSeed, cfg.Limits.MaxRounds, P);
    var legal = new List<GameAction>(32);
    var buf = new List<GameAction>(32);
    ulong rng = Rng.Mix(gameSeed ^ 0x51ED270B0DEADBEFUL);
    var rows = new float[GameConstants.MaxPlayers][];
    for (int i = 0; i < rows.Length; i++) rows[i] = new float[model.Features.Count];
    var scratch = new float[model.Features.ScratchLength];
    var reward = new double[GameConstants.MaxPlayers];
    var wins = new double[GameConstants.MaxPlayers];
    var local = new Dictionary<string, Group[]>();
    int decisions = 0;
    while (!state.IsOver && decisions < cfg.Limits.MaxDecisionsPerGame)
    {
        Rules.GetLegalActions(state, legal);
        if (legal.Count >= 2 && Rng.NextInt(ref rng, 100000) < RootProbability * 100000)
        {
            // choose up to MaxActions of the legal actions
            var acts = legal.ToList();
            while (acts.Count > MaxActions) acts.RemoveAt(Rng.NextInt(ref rng, acts.Count));
            int me = state.Actor;
            var truth = new double[acts.Count];
            var est = new double[Ns.Length][]; var single = new double[Ns.Length][];
            for (int ni = 0; ni < Ns.Length; ni++) { est[ni] = new double[acts.Count]; single[ni] = new double[acts.Count]; }
            for (int ai = 0; ai < acts.Count; ai++)
            {
                var sa = state.Clone();
                Rules.Apply(sa, acts[ai]);
                double sum = 0;
                for (int k = 0; k < K; k++)
                {
                    var s = sa.Clone();
                    ulong cs = Rng.Mix(gameSeed ^ (0x9E3779B97F4A7C15UL * (ulong)(k + 1)) ^ (ulong)(decisions * 31 + ai));
                    s.ReseedRng(cs);
                    PlayOut(s, GameRunner.CreateStrategies(cfg, seatToConfig, cs), cfg.Limits.MaxDecisionsPerGame);
                    MctsStrategy.TerminalReward(s, reward, wins);
                    sum += reward[me];
                }
                truth[ai] = sum / K;
                for (int ni = 0; ni < Ns.Length; ni++)
                {
                    double acc = 0, sq = 0;
                    for (int j = 0; j < S; j++)
                    {
                        var s = sa.Clone();
                        s.ReseedRng(Rng.Mix(gameSeed ^ (0xD1B54A32D192ED03UL * (ulong)(j + 1)) ^ (ulong)(decisions * 131 + ai * 7 + ni)));
                        int d = 0;
                        while (!s.IsOver && d < Ns[ni])
                        {
                            Rules.GetLegalActions(s, buf);
                            Rules.Apply(s, buf[buf.Count == 1 ? 0 : Rng.NextInt(ref rng, buf.Count)]);
                            d++;
                        }
                        double v;
                        if (s.IsOver) { MctsStrategy.TerminalReward(s, reward, wins); v = reward[me]; }
                        else { model.Features.ExtractAll(s, rows, scratch); v = Math.Clamp(model.Predict(rows[me]), 0, 1); }
                        acc += v; sq += (v - truth[ai]) * (v - truth[ai]);
                    }
                    est[ni][ai] = acc / S; single[ni][ai] = sq / S;
                }
            }
            string round = state.Round <= 5 ? "round 1-5" : state.Round <= 10 ? "round 6-10" : "round 11+";
            foreach (var key in new[] { "all", round, "phase " + state.Phase })
            {
                if (!local.TryGetValue(key, out var gr)) local[key] = gr = Enumerable.Range(0, Ns.Length).Select(_ => new Group()).ToArray();
                for (int ni = 0; ni < Ns.Length; ni++) gr[ni].Add(truth, est[ni], single[ni], S);
            }
        }
        var action = legal.Count == 1 ? legal[0] : strategies[state.Actor].ChooseAction(state, legal);
        Rules.Apply(state, action);
        decisions++;
    }
    lock (gate)
        foreach (var kv in local)
        {
            if (!groups.TryGetValue(kv.Key, out var gr)) groups[kv.Key] = gr = Enumerable.Range(0, Ns.Length).Select(_ => new Group()).ToArray();
            for (int ni = 0; ni < Ns.Length; ni++) gr[ni].Merge(kv.Value[ni]);
        }
});

Console.WriteLine($"{Path.GetFileName(args[0])}, model {Path.GetFileName(args[1])}, {gamesNeeded} games, K {K}, S {S}, took {(DateTime.UtcNow - started).TotalSeconds:0} s");
foreach (var key in groups.Keys.OrderBy(k => k == "all" ? "" : k))
{
    var gr = groups[key];
    Console.WriteLine();
    Console.WriteLine($"**{key}** ({gr[0].Roots:N0} roots, {gr[0].Actions:N0} actions)");
    Console.WriteLine("| leafRollout | top-1 agrees with truth | regret | pairs ordered correctly | leaf bias^2 (mean of S) | leaf MSE (one sample) |");
    Console.WriteLine("|---|---|---|---|---|---|");
    Console.WriteLine($"| random pick | {100 * gr[0].RandomTop1 / Math.Max(1, gr[0].Roots):0.0} % | {gr[0].RandomRegret / Math.Max(1, gr[0].Roots):0.0000} | 50.0 % | - | - |");
    for (int ni = 0; ni < Ns.Length; ni++)
    {
        var x = gr[ni];
        Console.WriteLine($"| {Ns[ni]} | {100.0 * x.Top1 / Math.Max(1, x.Roots):0.0} % | {x.Regret / Math.Max(1, x.Roots):0.0000} | {100.0 * x.PairsOk / Math.Max(1, x.Pairs):0.0} % | {x.Bias2 / Math.Max(1, x.Actions):0.0000} | {x.Mse1 / Math.Max(1, x.Actions):0.0000} |");
    }
}
Console.WriteLine();
Console.WriteLine("truth = hand-written continuation of the table (a proxy for competent play, not the real optimum); regret in reward units (0.6 win + 0.4 rank score).");
return 0;

static void PlayOut(GameState s, IStrategy[] strategies, int maxDecisions)
{
    var legal = new List<GameAction>(32);
    int decisions = 0;
    while (!s.IsOver)
    {
        Rules.GetLegalActions(s, legal);
        var action = legal.Count == 1 ? legal[0] : strategies[s.Actor].ChooseAction(s, legal);
        Rules.Apply(s, action);
        if (++decisions >= maxDecisions && !s.IsOver) Rules.ForceEnd(s, EndFlags.DecisionLimit);
    }
}

sealed class Group
{
    public long Roots, Actions, Top1, Pairs, PairsOk;
    public double Regret, Bias2, Mse1, RandomTop1, RandomRegret;

    public void Add(double[] truth, double[] est, double[] single, int S)
    {
        int n = truth.Length;
        Roots++; Actions += n;
        int bt = 0, be = 0;
        for (int i = 1; i < n; i++) { if (truth[i] > truth[bt]) bt = i; if (est[i] > est[be]) be = i; }
        if (be == bt) Top1++;
        Regret += truth[bt] - truth[be];
        RandomTop1 += 1.0 / n;
        RandomRegret += truth[bt] - truth.Average();
        for (int i = 0; i < n; i++)
        {
            Bias2 += (est[i] - truth[i]) * (est[i] - truth[i]);   // includes the noise of the average of S samples (about var / S): small for S >= 30
            Mse1 += single[i];
            for (int j = i + 1; j < n; j++)
                if (Math.Abs(truth[i] - truth[j]) >= 0.03) { Pairs++; if ((est[i] - est[j]) * (truth[i] - truth[j]) > 0) PairsOk++; }
        }
    }

    public void Merge(Group o)
    {
        Roots += o.Roots; Actions += o.Actions; Top1 += o.Top1; Pairs += o.Pairs; PairsOk += o.PairsOk;
        Regret += o.Regret; Bias2 += o.Bias2; Mse1 += o.Mse1; RandomTop1 += o.RandomTop1; RandomRegret += o.RandomRegret;
    }
}
