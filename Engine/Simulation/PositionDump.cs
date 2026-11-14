using System.Text.Json;
using PuertoRico.Engine.Events;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Strategies.Mcts;

namespace PuertoRico.Engine.Simulation;

/// <summary>
/// Training data for the learned value function (ml/): plays the configured games and samples decision points;
/// every sampled position gives one row per seat (features from that seat's view, <see cref="ValueFeatures"/>)
/// labelled with that seat's final MCTS reward (0.6 × win + 0.4 × rank score) and win share.
/// Output: <c>&lt;out&gt;</c> = fixed-size little-endian records (float32 reward, float32 win, int32 game, int16 × feature count),
/// <c>&lt;out&gt;.json</c> = metadata (feature names, layout, config). Deterministic in (config, game index, rate) and
/// independent of the thread count: games run in parallel in chunks and are written in game order.
/// </summary>
public static class PositionDump
{
    public const string Format = "pr-positions";
    public const int FormatVersion = 1;
    private const int Chunk = 64;

    public sealed record Summary(long Rows, int Games, long Positions);

    public static int RecordBytes => 4 + 4 + 4 + 2 * ValueFeatures.Count;

    private sealed class SampleSink : IGameEventSink
    {
        private ulong _rng;
        private readonly double _rate;
        public readonly List<float[][]> Positions = new();
        private readonly float[] _scratch = new float[ValueFeatures.ScratchLength];
        public SampleSink(ulong seed, double rate) { _rng = seed; _rate = rate; }
        public bool Enabled => true;
        public void OnDecision(GameState before, GameAction action)
        {
            if ((Rng.Next(ref _rng) >> 11) * (1.0 / (1UL << 53)) >= _rate) return;
            var rows = new float[before.PlayerCount][];
            for (int i = 0; i < rows.Length; i++) rows[i] = new float[ValueFeatures.Count];
            ValueFeatures.ExtractAll(before, rows, _scratch);
            Positions.Add(rows);
        }
    }

    public static Summary Run(SimulationConfig cfg, string outPath, double rate, IProgress<int>? progress = null, CancellationToken cancel = default)
    {
        if (rate <= 0 || rate > 1) throw new ArgumentException("--dump-rate must be in (0, 1]");
        string? dir = Path.GetDirectoryName(Path.GetFullPath(outPath));
        if (dir != null) Directory.CreateDirectory(dir);
        int f = ValueFeatures.Count;
        long rows = 0, positions = 0;
        int done = 0;
        var po = new ParallelOptions { MaxDegreeOfParallelism = cfg.Parallelism.MaxDegree > 0 ? cfg.Parallelism.MaxDegree : Environment.ProcessorCount, CancellationToken = cancel };
        using (var fs = new FileStream(outPath, FileMode.Create, FileAccess.Write))
        using (var w = new BinaryWriter(fs))
        {
            for (int start = 0; start < cfg.Games; start += Chunk)
            {
                int n = Math.Min(Chunk, cfg.Games - start);
                var per = new (List<float[][]> Pos, double[] Reward, double[] Win)[n];
                Parallel.For(0, n, po, k =>
                {
                    int game = start + k;
                    var sink = new SampleSink(Rng.Mix(SeedDeriver.GameSeed(cfg.Seed, game) ^ 0x5D0F_3A11_7C2B_9E41UL), rate);
                    GameRunner.Play(cfg, game, sink, out var final);
                    var reward = new double[GameConstants.MaxPlayers];
                    var win = new double[GameConstants.MaxPlayers];
                    MctsStrategy.TerminalReward(final, reward, win);
                    per[k] = (sink.Positions, reward, win);
                });
                for (int k = 0; k < n; k++)
                {
                    var (pos, reward, win) = per[k];
                    foreach (var p in pos)
                    {
                        positions++;
                        for (int seat = 0; seat < p.Length; seat++)
                        {
                            w.Write((float)reward[seat]);
                            w.Write((float)win[seat]);
                            w.Write(start + k);
                            var row = p[seat];
                            for (int i = 0; i < f; i++) w.Write(checked((short)row[i]));
                            rows++;
                        }
                    }
                }
                done += n;
                progress?.Report(done);
            }
        }

        var meta = new
        {
            format = Format,
            formatVersion = FormatVersion,
            featureVersion = ValueFeatures.Version,
            recordBytes = RecordBytes,
            layout = "float32 reward, float32 win, int32 game, int16[featureCount] features (little-endian)",
            featureCount = f,
            featureNames = ValueFeatures.Names,
            rows,
            positions,
            games = done,
            rate,
            players = cfg.Players,
            seed = cfg.Seed,
            seatOrder = cfg.SeatOrder.ToString(),
            seats = cfg.Seats.Select(s => new { s.Id, s.Strategy, s.Params }).ToList(),
        };
        File.WriteAllText(outPath + ".json", JsonSerializer.Serialize(meta, SimulationConfig.JsonOptions));
        return new Summary(rows, done, positions);
    }
}
