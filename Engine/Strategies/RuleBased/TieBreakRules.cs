using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// The second criterion of the hand-written strategies: it only decides between actions whose main scores are exactly equal
/// (compared lexicographically, so it can never override a real score difference). Everything is off by default: without any rule
/// the first action in engine order wins, the behaviour of every published result.
/// <para>Fixed orders (strings in the seat's <c>params</c>, tokens separated by <c>&gt;</c> or commas, most preferred first, unlisted tokens last):</para>
/// <list type="bullet">
/// <item><c>tieTile</c>: Settler phase: <c>corn indigo sugar tobacco coffee quarry hacienda</c></item>
/// <item><c>tieGood</c>: Craftsman bonus, selling, loading ships, keeping goods: <c>corn indigo sugar tobacco coffee</c></item>
/// <item><c>tieRole</c>: choosing a role: <c>settler mayor builder craftsman trader captain prospector</c></item>
/// <item><c>tieBuild</c>: Builder phase: lower-case building names (<c>smallmarket</c>, <c>wharf</c>, ...) and <c>pass</c></item>
/// </list>
/// <para>Reserved for the feature-weight version (docs/strategy-analysis.md section 8): <c>tieOpponent</c>, the weight of
/// <see cref="OpponentDependence"/> (default 0 = unused), the number of barrels the opponents currently produce of the good: positive prefers
/// goods the opponents depend on (blocking), negative avoids them. It is the second key after the fixed order and uses public information only.</para>
/// </summary>
/// <summary>Second criterion of one action: the fixed-order part, the opponent-dependence part, and the rank (-1 = no rule) for display.</summary>
public readonly record struct TieScore(double Order, double Opponent, int Rank)
{
    /// <summary>Lexicographic: the fixed order first, the opponent dependence second.</summary>
    public int CompareTo(TieScore other) => Order != other.Order ? Order.CompareTo(other.Order) : Opponent.CompareTo(other.Opponent);
    public static readonly TieScore None = new(0, 0, -1);
}

public sealed class TieBreakRules
{
    private static readonly string[] Goods = Enum.GetNames<Good>().Select(n => n.ToLowerInvariant()).ToArray();
    private static readonly string[] Roles = Enum.GetNames<Role>().Select(n => n.ToLowerInvariant()).ToArray();
    private static readonly string[] TileTokens = Goods.Concat(new[] { "quarry", "hacienda" }).ToArray();
    private static readonly string[] BuildTokens = Enum.GetNames<BuildingId>().Select(n => n.ToLowerInvariant()).Concat(new[] { "pass" }).ToArray();

    private readonly Dictionary<string, int>? _tile, _good, _role, _build;
    private readonly double _opponentWeight;

    /// <summary>False when no rule is set: nothing is computed and the engine order decides.</summary>
    public bool Active { get; }

    private TieBreakRules(IReadOnlyDictionary<string, JsonElement> p)
    {
        _tile = Parse(p, "tieTile", TileTokens);
        _good = Parse(p, "tieGood", Goods);
        _role = Parse(p, "tieRole", Roles);
        _build = Parse(p, "tieBuild", BuildTokens);
        _opponentWeight = StrategyRegistry.GetDouble(p, "tieOpponent", 0);
        Active = _tile != null || _good != null || _role != null || _build != null || _opponentWeight != 0;
    }

    public static TieBreakRules From(IReadOnlyDictionary<string, JsonElement> parameters) => new(parameters);

    private static Dictionary<string, int>? Parse(IReadOnlyDictionary<string, JsonElement> p, string key, string[] vocabulary)
    {
        string text = StrategyRegistry.GetString(p, key, "");
        if (string.IsNullOrWhiteSpace(text)) return null;
        var order = new Dictionary<string, int>();
        foreach (var raw in text.Split(new[] { '>', ',' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            string token = raw.ToLowerInvariant();
            if (!vocabulary.Contains(token))
                throw new ArgumentException($"Unknown token '{raw}' in {key}. Known: {string.Join(", ", vocabulary)}");
            if (!order.ContainsKey(token)) order[token] = order.Count;
        }
        return order;
    }

    /// <summary>
    /// Second criterion of an action (higher is preferred): the fixed-order part (<c>-rank</c>, unlisted tokens rank after all listed ones;
    /// <see cref="TieRank"/> is the rank, -1 when no rule applies) and the opponent-dependence part (0 while its weight is 0).
    /// </summary>
    public TieScore Score(GameState s, int me, GameAction a)
    {
        var (dict, token) = Rule(a, s.Phase);
        int rank = -1;
        double order = 0;
        if (dict != null)
        {
            rank = token != null && dict.TryGetValue(token, out var r) ? r : dict.Count;
            order = -rank;
        }
        double opp = _opponentWeight != 0 && GoodOf(a) is int g ? _opponentWeight * OpponentDependence(s, me, g) : 0;
        return new TieScore(order, opp, rank);
    }

    /// <summary>Barrels the opponents of <paramref name="me"/> produce of <paramref name="good"/> right now (occupied plantations and producer circles; public information).</summary>
    public static double OpponentDependence(GameState s, int me, int good)
    {
        double n = 0;
        for (int p = 0; p < s.PlayerCount; p++)
            if (p != me) n += Rules.ProductionOf(s, p, good);
        return n;
    }

    private (Dictionary<string, int>? Dict, string? Token) Rule(GameAction a, Phase phase)
    {
        switch (a.Type)
        {
            case ActionType.TakePlantation: return (_tile, Goods[a.A]);
            case ActionType.TakeQuarry: return (_tile, "quarry");
            case ActionType.UseHacienda: return (_tile, "hacienda");
            case ActionType.ChooseRole: return (_role, Roles[a.A]);
            case ActionType.Build: return (_build, BuildTokens[a.A]);
            case ActionType.CraftsmanBonus:
            case ActionType.Sell:
            case ActionType.LoadShip:
            case ActionType.LoadWharf:
            case ActionType.KeepGoods:
            case ActionType.KeepBarrel: return (_good, Goods[a.A]);
            case ActionType.Pass:
                return phase switch { Phase.Settler => (_tile, null), Phase.Builder => (_build, "pass"), _ => (_good, null) };
            default: return (null, null);
        }
    }

    private static int? GoodOf(GameAction a) => a.Type switch
    {
        ActionType.TakePlantation or ActionType.CraftsmanBonus or ActionType.Sell or ActionType.LoadShip or ActionType.LoadWharf
            or ActionType.KeepGoods or ActionType.KeepBarrel => a.A,
        _ => null,
    };
}
