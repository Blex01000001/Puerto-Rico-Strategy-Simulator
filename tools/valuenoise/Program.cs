using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies;
using PuertoRico.Engine.Strategies.Mcts;

// Run: dotnet run -c Release --project tools/valuenoise -- ml/data-configs/4p-hand-a.json ml/models/4p-v2.txt [games=200] [K=50] [rounds=3,6,9,12] [seed=777]
// How much of the value model's error is luck, and how much is the model? (docs/strategy-analysis.md section 10, TODO 8 D2)
// Plays games of a hand-written table (the config's seats, fixed strategies) and, at the first decision of each chosen round, takes the position
// and plays the rest of the game K more times with different random seeds (same strategies; the chance events — tile draws, plantation
// draws, ... — differ). For every seat:
//   mean   = average reward over the K continuations (0.6 x win + 0.4 x rank score = the model's training label)
//   noise  = variance of the reward between the continuations = what a single game outcome adds on top of the position's true value
//   bias2  = (model prediction - mean)^2 minus noise / K (the mean of K continuations is itself noisy) = what a better model could still fix
// The model's MSE against single outcomes (what training and validation measure) is about bias2 + noise, so noise is the floor of that MSE
// for hand-written continuation play, and bias2 / (bias2 + noise) is the share of the error that is the model's. Values are averaged over seats.
if (args.Length < 2) { Console.Error.WriteLine("usage: valuenoise <config.json> <model> [games] [K] [rounds] [seed]"); return 1; }
var cfg = SimulationConfig.Load(args[0]);
var model = ValueModels.Load(args[1]);
int games = args.Length > 2 ? int.Parse(args[2]) : 200;
int K = args.Length > 3 ? int.Parse(args[3]) : 50;
var rounds = (args.Length > 4 ? args[4] : "3,6,9,12").Split(',').Select(int.Parse).ToArray();
ulong seed = args.Length > 5 ? ulong.Parse(args[5]) : 777;
int P = cfg.Players;
if (K < 2) { Console.Error.WriteLine("K must be at least 2"); return 1; }
if (cfg.Seats.Any(s => s.Strategy.Equals("mcts", StringComparison.OrdinalIgnoreCase))) { Console.Error.WriteLine("this tool plays the continuations itself: use a hand-written table (no mcts seat)"); return 1; }

var acc = rounds.ToDictionary(r => r, _ => new Acc());
var gate = new object();
var started = DateTime.UtcNow;
Parallel.For(0, games, g =>
{
    ulong gameSeed = SeedDeriver.GameSeed(seed, g);
    int[] seatToConfig = GameRunner.SeatAssignment(cfg, g, gameSeed);
    var strategies = GameRunner.CreateStrategies(cfg, seatToConfig, gameSeed);
    var state = Setup.NewGame(gameSeed, cfg.Limits.MaxRounds, P);
    var legal = new List<GameAction>(32);
    var done = new HashSet<int>();
    var local = new List<(int Round, double Noise, double Bias2, double Mse1, int N)>();
    var reward = new double[GameConstants.MaxPlayers];
    var wins = new double[GameConstants.MaxPlayers];
    var rows = new float[GameConstants.MaxPlayers][];
    for (int i = 0; i < rows.Length; i++) rows[i] = new float[model.Features.Count];
    var scratch = new float[model.Features.ScratchLength];
    int decisions = 0;
    while (!state.IsOver && decisions < cfg.Limits.MaxDecisionsPerGame)
    {
        if (rounds.Contains(state.Round) && done.Add(state.Round))
        {
            var snap = state.Clone();
            model.Features.ExtractAll(snap, rows, scratch);
            var sum = new double[P]; var sumSq = new double[P];
            for (int k = 0; k < K; k++)
            {
                var s = snap.Clone();
                ulong contSeed = Rng.Mix(gameSeed ^ (0x9E3779B97F4A7C15UL * (ulong)(k + 1)) ^ (ulong)snap.Round);
                s.ReseedRng(contSeed);
                var strat = GameRunner.CreateStrategies(cfg, seatToConfig, contSeed);
                PlayOut(s, strat, cfg.Limits.MaxDecisionsPerGame);
                MctsStrategy.TerminalReward(s, reward, wins);
                for (int seat = 0; seat < P; seat++) { sum[seat] += reward[seat]; sumSq[seat] += reward[seat] * reward[seat]; }
            }
            double noise = 0, bias2 = 0, mse1 = 0;
            for (int seat = 0; seat < P; seat++)
            {
                double mean = sum[seat] / K;
                double var = Math.Max(0, (sumSq[seat] - K * mean * mean) / (K - 1));
                double pred = Math.Clamp(model.Predict(rows[seat]), 0, 1);
                double err = (pred - mean) * (pred - mean);
                noise += var; bias2 += err - var / K;
                mse1 += err + var * (K - 1.0) / K;   // expected squared error against one outcome
            }
            lock (gate) acc[snap.Round].Add(noise / P, bias2 / P, mse1 / P);
        }
        Rules.GetLegalActions(state, legal);
        var action = legal.Count == 1 ? legal[0] : strategies[state.Actor].ChooseAction(state, legal);
        Rules.Apply(state, action);
        decisions++;
    }
});

Console.WriteLine($"{Path.GetFileName(args[0])}, model {Path.GetFileName(args[1])}, {games} games, K {K}, took {(DateTime.UtcNow - started).TotalSeconds:0} s");
Console.WriteLine();
Console.WriteLine("| round | positions | noise (variance between continuations) | model error beyond noise (bias^2) | MSE vs one outcome (noise + bias^2) | model's share of the error |");
Console.WriteLine("|---|---|---|---|---|---|");
foreach (var r in rounds)
{
    var a = acc[r];
    if (a.N == 0) { Console.WriteLine($"| {r} | 0 | - | - | - | - |"); continue; }
    double noise = a.Noise / a.N, bias = Math.Max(0, a.Bias2 / a.N);
    Console.WriteLine($"| {r} | {a.N:N0} | {noise:0.0000} | {a.Bias2 / a.N:0.0000} | {noise + bias:0.0000} | {100 * bias / Math.Max(1e-12, noise + bias):0.0} % |");
}
Console.WriteLine();
Console.WriteLine("noise = floor of the MSE for these hand-written strategies; bias^2 = what a better model could still gain (negative values are estimation noise and count as 0).");
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

sealed class Acc
{
    public double Noise, Bias2;
    public long N;
    public void Add(double noise, double bias2, double mse1) { Noise += noise; Bias2 += bias2; N++; }
}
