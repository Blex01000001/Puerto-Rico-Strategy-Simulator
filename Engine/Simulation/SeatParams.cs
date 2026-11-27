using System.Globalization;
using System.Text.Json;
using PuertoRico.Engine.Strategies;

namespace PuertoRico.Engine.Simulation;

/// <summary>
/// A seat's parameters as typed into a form (name -> text) and back: the logic behind the Dashboard's 策略模擬 page
/// (one input box per parameter, filled with the default), kept here so it is unit-tested (Tests/SeatParamsTests.cs).
/// The ML UI's custom seats follow the same rules (ml/mlui/pipeline.py; the MCTS order comes from ml/engine-info.json).
/// </summary>
public static class SeatParams
{
    /// <summary>MCTS: the parameters people change most, shown first (in this order) by both UIs.</summary>
    public static readonly IReadOnlyList<string> MctsFirst = new[] { "valueModel", "simulations", "leafRollout", "rolloutRounds", "rolloutStrategy" };

    /// <summary>The seat orders in the order both UIs offer them (the default, random, first; rotate and fixed are not recommended).</summary>
    public static readonly IReadOnlyList<string> SeatOrders = new[] { "random", "balanced", "rotate", "fixed" };

    /// <summary>A parameter value as the text of its input box (numbers in invariant format).</summary>
    public static string Text(JsonElement v) => v.ValueKind switch
    {
        JsonValueKind.Number => v.GetDouble().ToString("R", CultureInfo.InvariantCulture),
        JsonValueKind.String => v.GetString() ?? "",
        _ => v.ToString(),
    };

    private static bool TryNumber(string text, out double value) =>
        double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value);

    /// <summary>
    /// The parameters of <paramref name="strategy"/> with the values it uses by default with <paramref name="players"/>
    /// players (what the engine resolves). For MCTS the chosen value model counts: some defaults (leafRollout) depend on
    /// whether there is one; the entry <c>valueModel</c> itself is "" (the default is no model). A model that cannot be
    /// loaded falls back to the defaults without a model; an unknown strategy has no parameters.
    /// </summary>
    public static Dictionary<string, JsonElement> Defaults(string strategy, int players, string valueModel = "")
    {
        if (!strategy.Equals("mcts", StringComparison.OrdinalIgnoreCase)) valueModel = "";
        try
        {
            var seat = new SeatConfig { Strategy = strategy };
            if (valueModel.Length > 0) seat.Params["valueModel"] = JsonSerializer.SerializeToElement(valueModel);
            var d = StrategyRegistry.Resolve(seat, players).Params;
            d.Remove("valueModel");
            d["valueModel"] = JsonSerializer.SerializeToElement("");
            return d;
        }
        catch (Exception e) when (e is ArgumentException or InvalidOperationException or KeyNotFoundException or IOException)
        {
            return valueModel.Length > 0 ? Defaults(strategy, players) : new();
        }
    }

    /// <summary>The order of a seat's input boxes: <paramref name="keys"/> as given, but for MCTS <see cref="MctsFirst"/> first.</summary>
    public static List<string> Order(string strategy, IEnumerable<string> keys)
    {
        var list = keys.ToList();
        if (!strategy.Equals("mcts", StringComparison.OrdinalIgnoreCase)) return list;
        return MctsFirst.Where(list.Contains).Concat(list.Where(k => !MctsFirst.Contains(k))).ToList();
    }

    /// <summary>
    /// Whether a typed value means "the default": an empty box, or the default itself (numbers compared by value), so a
    /// default that depends on other settings (leafRollout with a model) keeps following them.
    /// </summary>
    public static bool IsDefault(string? value, JsonElement? def)
    {
        value = (value ?? "").Trim();
        if (value.Length == 0) return true;
        if (def is not { } d) return false;
        return d.ValueKind == JsonValueKind.Number
            ? TryNumber(value, out var v) && v == d.GetDouble()
            : string.Equals(value, Text(d), StringComparison.Ordinal);
    }

    /// <summary>
    /// The typed values of a seat as engine parameters. A parameter whose default is a number must be a number (otherwise
    /// <paramref name="badKey"/> names it and the result stops there); an unknown name keeps what was typed (a number if it parses).
    /// </summary>
    public static Dictionary<string, JsonElement> Build(IReadOnlyDictionary<string, string> typed, IReadOnlyDictionary<string, JsonElement> defaults,
        out string? badKey)
    {
        badKey = null;
        var result = new Dictionary<string, JsonElement>();
        foreach (var (key, text) in typed)
        {
            bool isNumber = TryNumber(text, out var v);
            if (defaults.TryGetValue(key, out var def) && def.ValueKind == JsonValueKind.Number)
            {
                if (!isNumber) { badKey = key; return result; }
                result[key] = JsonSerializer.SerializeToElement(v);
            }
            else result[key] = isNumber && !defaults.ContainsKey(key) ? JsonSerializer.SerializeToElement(v) : JsonSerializer.SerializeToElement(text);
        }
        return result;
    }

    /// <summary>
    /// Seat ids = the names shown in the results: the strategy name, an MCTS seat with a value model carries the model's
    /// name (<c>mcts(4p-v2)</c>), and a name used more than once is numbered on every seat (<c>#1</c>, <c>#2</c>…).
    /// </summary>
    public static List<string> Ids(IReadOnlyList<SeatConfig> seats)
    {
        var labels = seats.Select(s =>
            s.Params.TryGetValue("valueModel", out var vm) && vm.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(vm.GetString())
                ? $"{s.Strategy}({Path.GetFileNameWithoutExtension(vm.GetString())})"
                : s.Strategy).ToList();
        var count = labels.GroupBy(l => l).ToDictionary(g => g.Key, g => g.Count());
        var seen = new Dictionary<string, int>();
        return labels.Select(l =>
        {
            seen[l] = seen.GetValueOrDefault(l) + 1;
            return count[l] == 1 ? l : $"{l}#{seen[l]}";
        }).ToList();
    }
}
