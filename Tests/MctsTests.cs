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
