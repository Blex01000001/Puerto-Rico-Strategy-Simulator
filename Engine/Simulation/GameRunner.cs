using PuertoRico.Engine.Events;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Strategies;

namespace PuertoRico.Engine.Simulation;

public static class GameRunner
{
    /// <summary>Table seat -> config seat index for this game.</summary>
    public static int[] SeatAssignment(SimulationConfig cfg, int gameIndex, ulong gameSeed)
    {
        int n = GameConstants.Players;
        var map = new int[n];
        switch (cfg.SeatOrder)
        {
            case SeatOrderMode.Fixed:
                for (int i = 0; i < n; i++) map[i] = i;
                break;
            case SeatOrderMode.Rotate:
                for (int i = 0; i < n; i++) map[i] = ((i - gameIndex) % n + n) % n;
                break;
            default:
                for (int i = 0; i < n; i++) map[i] = i;
                ulong rng = SeedDeriver.SeatSeed(gameSeed);
                for (int i = n - 1; i > 0; i--)
                {
                    int j = Rng.NextInt(ref rng, i + 1);
                    (map[i], map[j]) = (map[j], map[i]);
                }
                break;
        }
        return map;
    }

    public static string EndReasonText(EndFlags flags)
    {
        var parts = new List<string>();
        if ((flags & EndFlags.VpExhausted) != 0) parts.Add("vpExhausted");
        if ((flags & EndFlags.ColonistsShort) != 0) parts.Add("colonistsShort");
        if ((flags & EndFlags.CityFull) != 0) parts.Add("cityFull");
        if ((flags & EndFlags.RoundLimit) != 0) parts.Add("roundLimit");
        if ((flags & EndFlags.DecisionLimit) != 0) parts.Add("decisionLimit");
        return string.Join("+", parts);
    }

    /// <summary>Plays one complete game. Deterministic in (config, gameIndex).</summary>
    public static GameRecord Play(SimulationConfig cfg, int gameIndex, IGameEventSink? sink = null) =>
        Play(cfg, gameIndex, sink, out _);

    public static GameRecord Play(SimulationConfig cfg, int gameIndex, IGameEventSink? sink, out GameState finalState)
    {
        sink ??= NullEventSink.Instance;
        ulong gameSeed = SeedDeriver.GameSeed(cfg.Seed, gameIndex);
        int[] seatToConfig = SeatAssignment(cfg, gameIndex, gameSeed);

        var strategies = new IStrategy[GameConstants.Players];
        for (int seat = 0; seat < strategies.Length; seat++)
        {
            int ci = seatToConfig[seat];
            var sc = cfg.Seats[ci];
            strategies[seat] = StrategyRegistry.Create(sc.Strategy, sc.Params, SeedDeriver.StrategySeed(gameSeed, ci), seat);
        }

        var state = Setup.NewGame(gameSeed, cfg.Limits.MaxRounds);
        var legal = new List<GameAction>(32);
        bool auto = cfg.Options.AutoAdvanceForced;
        int decisions = 0;

        while (!state.IsOver)
        {
            Rules.GetLegalActions(state, legal);
            if (legal.Count == 0) throw new InvalidOperationException($"No legal action in phase {state.Phase} (game {gameIndex})");
            var action = auto && legal.Count == 1 ? legal[0] : strategies[state.Actor].ChooseAction(state, legal);
            if (sink.Enabled) sink.OnDecision(state, action);
            Rules.Apply(state, action);
            if (++decisions >= cfg.Limits.MaxDecisionsPerGame && !state.IsOver)
                Rules.ForceEnd(state, EndFlags.DecisionLimit);
        }

        var score = Scoring.Score(state);
        var record = new GameRecord
        {
            Index = gameIndex,
            Seed = gameSeed,
            Rounds = state.Round - 1,
            Decisions = decisions,
            EndReason = EndReasonText(state.EndFlags),
            Winners = score.Winners.ToList(),
        };
        foreach (var p in score.Players)
        {
            record.Players.Add(new PlayerRecord
            {
                Seat = p.Seat,
                SeatId = cfg.Seats[seatToConfig[p.Seat]].Id,
                Vp = p.Total,
                Chips = p.Chips,
                BuildingPoints = p.BuildingPoints,
                BonusPoints = p.BonusPoints,
                Tiebreak = p.Tiebreak,
                Rank = p.Rank,
            });
        }
        finalState = state;
        return record;
    }
}
