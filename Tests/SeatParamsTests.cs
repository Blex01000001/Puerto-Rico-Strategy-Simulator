using System.Text.Json;
using PuertoRico.Engine.Simulation;

namespace PuertoRico.Tests;

/// <summary>SeatParams: the Dashboard's seat parameter boxes (typed text &lt;-&gt; engine parameters, seat ids).</summary>
public class SeatParamsTests
{
    private static JsonElement J(object v) => JsonSerializer.SerializeToElement(v);

    [Fact]
    public void Defaults_Are_What_The_Engine_Resolves_And_ValueModel_Is_Empty()
    {
        var d4 = SeatParams.Defaults("build-first", 4);
        var d3 = SeatParams.Defaults("build-first", 3);
        Assert.Equal(4.5, d4["buildThreshold"].GetDouble());
        Assert.Equal(3.5, d3["buildThreshold"].GetDouble());
        Assert.Equal("", SeatParams.Defaults("mcts", 4)["valueModel"].GetString());
        Assert.Empty(SeatParams.Defaults("no-such-strategy", 4));
        // a model that cannot be loaded: the defaults without a model
        Assert.Equal(SeatParams.Defaults("mcts", 4)["leafRollout"].GetDouble(),
                     SeatParams.Defaults("mcts", 4, "ml/models/no-such-model.txt")["leafRollout"].GetDouble());
    }

    [Fact]
    public void Mcts_Shows_Its_Most_Used_Parameters_First()
    {
        var order = SeatParams.Order("mcts", new[] { "exploration", "rolloutStrategy", "simulations", "valueModel" });
        Assert.Equal(new[] { "valueModel", "simulations", "rolloutStrategy", "exploration" }, order);
        Assert.Equal(new[] { "b", "a" }, SeatParams.Order("build-first", new[] { "b", "a" }));
    }

    [Fact]
    public void Every_Seat_Order_Is_Offered_Once()
    {
        Assert.Equal(Enum.GetNames<SeatOrderMode>().Select(n => n.ToLowerInvariant()).OrderBy(n => n),
                     SeatParams.SeatOrders.OrderBy(n => n));
        Assert.Equal("random", SeatParams.SeatOrders[0]);
    }

    [Theory]
    [InlineData("", true)]
    [InlineData("  ", true)]
    [InlineData("4.5", true)]
    [InlineData("4.50", true)]
    [InlineData("4", false)]
    [InlineData("x", false)]
    public void A_Value_Equal_To_The_Numeric_Default_Is_The_Default(string typed, bool isDefault) =>
        Assert.Equal(isDefault, SeatParams.IsDefault(typed, J(4.5)));

    [Fact]
    public void Text_Defaults_Compare_As_Text()
    {
        Assert.True(SeatParams.IsDefault("random", J("random")));
        Assert.False(SeatParams.IsDefault("Random", J("random")));
        Assert.False(SeatParams.IsDefault("1", null));
        Assert.Equal("0.1", SeatParams.Text(J(0.1)));
    }

    [Fact]
    public void Build_Turns_Text_Into_Numbers_Where_The_Default_Is_A_Number()
    {
        var defs = new Dictionary<string, JsonElement> { ["n"] = J(3), ["s"] = J("abc") };
        var p = SeatParams.Build(new Dictionary<string, string> { ["n"] = "7", ["s"] = "12", ["extra"] = "2.5", ["word"] = "hi" }, defs, out var bad);
        Assert.Null(bad);
        Assert.Equal(JsonValueKind.Number, p["n"].ValueKind);
        Assert.Equal(JsonValueKind.String, p["s"].ValueKind);     // a text parameter stays text even when it looks like a number
        Assert.Equal(2.5, p["extra"].GetDouble());                // unknown names: a number when it parses
        Assert.Equal("hi", p["word"].GetString());
        SeatParams.Build(new Dictionary<string, string> { ["n"] = "seven" }, defs, out bad);
        Assert.Equal("n", bad);
    }

    [Fact]
    public void Seat_Ids_Carry_The_Model_And_Number_Repeated_Names()
    {
        SeatConfig S(string strategy, string? model = null)
        {
            var s = new SeatConfig { Strategy = strategy };
            if (model != null) s.Params["valueModel"] = J(model);
            return s;
        }
        var ids = SeatParams.Ids(new[] { S("mcts", "ml/models/4p-v2.txt"), S("mcts", "ml/models/4p-v3.txt"), S("random"), S("random") });
        Assert.Equal(new[] { "mcts(4p-v2)", "mcts(4p-v3)", "random#1", "random#2" }, ids);
        Assert.Equal(new[] { "mcts" }, SeatParams.Ids(new[] { S("mcts", " ") }));
    }
}
