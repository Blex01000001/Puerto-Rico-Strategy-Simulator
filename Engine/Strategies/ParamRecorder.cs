using System.Diagnostics.CodeAnalysis;
using System.Text.Json;

namespace PuertoRico.Engine.Strategies;

/// <summary>
/// Implemented by strategies that read (some of) their parameters lazily, once the player count is known
/// (hand-written strategies: defaults differ between 3 and 4 players). <see cref="StrategyRegistry.Resolve"/> calls it
/// so every parameter is read without playing a game.
/// </summary>
public interface IResolvesParameters
{
    void ResolveParameters(int players);
}

/// <summary>
/// A seat's parameters that remembers what the strategy read and the value it used (<see cref="StrategyRegistry.GetDouble"/>
/// and <see cref="StrategyRegistry.GetString"/> record into it). Only used by <see cref="StrategyRegistry.Resolve"/>;
/// games get the plain dictionary.
/// </summary>
internal sealed class ParamRecorder : IReadOnlyDictionary<string, JsonElement>
{
    private readonly IReadOnlyDictionary<string, JsonElement> _inner;
    public readonly Dictionary<string, JsonElement> Used = new(StringComparer.Ordinal);

    public ParamRecorder(IReadOnlyDictionary<string, JsonElement> inner) => _inner = inner;

    public void Record(string key, object value) => Used[key] = JsonSerializer.SerializeToElement(value);

    public JsonElement this[string key] => _inner[key];
    public IEnumerable<string> Keys => _inner.Keys;
    public IEnumerable<JsonElement> Values => _inner.Values;
    public int Count => _inner.Count;
    public bool ContainsKey(string key) => _inner.ContainsKey(key);
    public bool TryGetValue(string key, [MaybeNullWhen(false)] out JsonElement value) => _inner.TryGetValue(key, out value);
    public IEnumerator<KeyValuePair<string, JsonElement>> GetEnumerator() => _inner.GetEnumerator();
    System.Collections.IEnumerator System.Collections.IEnumerable.GetEnumerator() => GetEnumerator();
}
