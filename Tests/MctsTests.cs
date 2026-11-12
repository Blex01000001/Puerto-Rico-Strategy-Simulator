using System.Text.Json;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies;
using Xunit;

namespace PuertoRico.Tests;

public class MctsTests
{
    private static JsonElement Num(double v) => JsonSerializer.SerializeToElement(v);

    private static SimulationConfig Config(int players, int sims, string rollout = "random")
    {
        var cfg = new SimulationConfig { Name = "mcts", Players = players, Games = 4, Seed = 99, Seats = new List<SeatConfig>() };
        var mcts = new SeatConfig { Id = "m", Strategy = "mcts" };
        mcts.Params["simulations"] = Num(sims);
        mcts.Params["rolloutStrategy"] = JsonSerializer.SerializeToElement(rollout);
        cfg.Seats.Add(mcts);
        for (int i = 1; i < players; i++) cfg.Seats.Add(new SeatConfig { Id = $"r{i}", Strategy = "random" });
        return cfg;
    }

    private sealed class CollectSink : PuertoRico.Engine.Events.IGameEventSink
    {
        public List<(int Seat, GameAction Action, SearchSummary? Search)> Items { get; } = new();
        private SearchSummary? _pending;
        public bool Enabled => true;
        public void OnSearch(SearchSummary search) => _pending = search;
        public void OnDecision(GameState before, GameAction action) { Items.Add((before.Actor, action, _pending)); _pending = null; }
    }

    [Fact]
    public void Replay_sink_receives_search_summary_only_for_mcts_decisions_with_a_choice()
    {
        var cfg = Config(3, sims: 8);
        var sink = new CollectSink();
        GameRunner.Play(cfg, 0, sink, out _);
        var mctsSeat = sink.Items.Where(i => i.Search != null).Select(i => i.Seat).Distinct().ToList();
        Assert.Single(mctsSeat); // only the MCTS player reports a search
        foreach (var (_, action, search) in sink.Items.Where(i => i.Search != null))
        {
            Assert.Equal(8, search!.Simulations);
            Assert.Equal(0.7, search.Exploration); // default UCT constant
            Assert.Equal("random", search.RolloutStrategy);
            Assert.Equal(8, search.RolloutRounds);
            foreach (var e in search.Actions)
            {
                // UCT = mean + exploration bonus: never below the mean, undefined for unvisited actions
                // reward = 0.6 × win + 0.4 × rank score, so the win rate is between 0 and reward / 0.6
                Assert.InRange(e.WinRate, 0, 1);
                Assert.True(e.StdError >= 0 && e.StdError <= 0.5 + 1e-9); // rewards lie in [0,1]
                Assert.True(0.6 * e.WinRate <= e.MeanReward + 1e-9);
                if (e.Visits == 0) Assert.Null(search.Uct(e));
                else Assert.True(search.Uct(e) >= e.MeanReward);
            }
            Assert.True(search.Actions.Count >= 2);
            Assert.Contains(search.Actions, e => e.Action == action);
            Assert.Equal(search.Actions.Max(e => e.Visits), search.Actions.First(e => e.Action == action).Visits);
        }
    }

    [Fact]
    public void Search_summary_has_principal_lines_with_the_acting_seat_and_visits_that_do_not_grow()
    {
        var cfg = Config(3, sims: 60);
        var sink = new CollectSink();
        GameRunner.Play(cfg, 0, sink, out _);
        var searches = sink.Items.Where(i => i.Search != null).Select(i => i.Search!).ToList();
        Assert.Contains(searches, sr => sr.Actions.Any(e => e.Line is { Count: > 0 }));
        foreach (var e in searches.SelectMany(sr => sr.Actions).Where(e => e.Line != null))
        {
            Assert.True(e.Line!.Count <= 8);
            int prev = e.Visits;
            foreach (var step in e.Line) { Assert.InRange(step.Seat, 0, 2); Assert.True(step.Visits <= prev); prev = step.Visits; }
        }
    }

    [Fact]
    public void ClearlyAhead_Needs_A_Gap_Larger_Than_The_Noise()
    {
        var a = GameAction.Pass;
        var ahead = new SearchSummary.Entry(a, 100, 0.60, null, 0, 0.02);
        var close = new SearchSummary.Entry(a, 100, 0.58, null, 0, 0.02);
        var far = new SearchSummary.Entry(a, 100, 0.40, null, 0, 0.02);
        Assert.False(SearchSummary.ClearlyAhead(ahead, close)); // gap 0.02 < 2 × sqrt(0.02² + 0.02²) = 0.057
        Assert.True(SearchSummary.ClearlyAhead(ahead, far));    // gap 0.20
        Assert.False(SearchSummary.ClearlyAhead(far, ahead));   // never the other way round
        Assert.False(SearchSummary.ClearlyAhead(ahead, new SearchSummary.Entry(a, 1, 0.0, null, 0, 0)));  // too few visits to tell
    }

    [Theory]
    [InlineData(3)]
    [InlineData(4)]
    public void Games_finish_with_only_legal_actions(int players)
    {
        var cfg = Config(players, sims: 6);
        for (int g = 0; g < 3; g++)
        {
            var rec = GameRunner.Play(cfg, g, null, out var final);
            Assert.True(final.IsOver);
            Assert.NotEmpty(rec.Winners);
            Assert.Null(Invariants.Check(final));
        }
    }

    [Theory]
    [InlineData(0)]
    [InlineData(2)]
    public void Truncated_and_full_rollouts_finish_games(int rolloutRounds)
    {
        var cfg = Config(3, sims: 5);
        cfg.Seats[0].Params["rolloutRounds"] = Num(rolloutRounds);
        var rec = GameRunner.Play(cfg, 0, null, out var final);
        Assert.True(final.IsOver);
        Assert.NotEmpty(rec.Winners);
    }

    [Fact]
    public void Guided_random_rollout_only_returns_legal_actions()
    {
        var cfg = Config(3, sims: 4, rollout: "guided-random");
        var rec = GameRunner.Play(cfg, 2, null, out var final);
        Assert.True(final.IsOver);
        var strategy = StrategyRegistry.Create("guided-random", new Dictionary<string, JsonElement>(), 7, 0);
        var s = Setup.NewGame(3, 150, 3);
        var legal = new List<GameAction>();
        for (int i = 0; i < 300 && !s.IsOver; i++)
        {
            Rules.GetLegalActions(s, legal);
            var a = strategy.ChooseAction(s, legal);
            Assert.Contains(a, legal);
            Rules.Apply(s, a);
        }
    }

    [Fact]
    public void Same_config_and_seed_reproduce_the_game()
    {
        var cfg = Config(3, sims: 8, rollout: "corn-shipper");
        var a = GameRunner.Play(cfg, 1);
        var b = GameRunner.Play(cfg, 1);
        Assert.Equal(a.Decisions, b.Decisions);
        Assert.Equal(a.Players.Select(p => p.Vp), b.Players.Select(p => p.Vp));
    }

    [Fact]
    public void Choosing_does_not_modify_the_state_it_is_given()
    {
        var s = Setup.NewGame(5, 150, 3);
        var legal = new List<GameAction>();
        Rules.GetLegalActions(s, legal);
        string before = JsonSerializer.Serialize(s);
        var strategy = StrategyRegistry.Create("mcts", new Dictionary<string, JsonElement> { ["simulations"] = Num(20) }, 3, 0);
        var action = strategy.ChooseAction(s, legal);
        Assert.Contains(action, legal);
        Assert.Equal(before, JsonSerializer.Serialize(s));
    }

    [Fact]
    public void Rollout_strategy_must_be_known_and_not_mcts()
    {
        Assert.Throws<ArgumentException>(() => StrategyRegistry.Create("mcts", new Dictionary<string, JsonElement> { ["rolloutStrategy"] = JsonSerializer.SerializeToElement("mcts") }, 1, 0));
        Assert.Throws<ArgumentException>(() => StrategyRegistry.Create("mcts", new Dictionary<string, JsonElement> { ["rolloutStrategy"] = JsonSerializer.SerializeToElement("nope") }, 1, 0));
    }
}
