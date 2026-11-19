namespace Dashboard.Services;

/// <summary>One tunable parameter of a strategy, for the descriptions on the simulate page.</summary>
public sealed record ParamInfo(string Name, string Default, string Meaning, string Range);

/// <summary>Display text for one strategy: what it does and what can be tuned. Defaults match the Engine (3 / 4 players).</summary>
public sealed record StrategyDoc(string Id, string Title, string Summary, string[] Rules, ParamInfo[] Params);

/// <summary>
/// The strategy descriptions. The texts live in i18n/dash.&lt;lang&gt;.json: strat.&lt;id&gt;.title / .summary / .rule.N (N from 0) /
/// .p.N.name, .p.N.default, .p.N.meaning, .p.N.range (N from 0), strat.group.&lt;key&gt;.title / .hint. Only the order and the
/// grouping are here; a strategy with more rules or parameters just needs more keys.
/// </summary>
public static class StrategyInfo
{
    private static readonly string[] Ids =
    {
        "corn-shipper", "corn-to-premium", "harbor-rush", "build-first", "cheap-engine", "wharf-rush", "wharf-premium",
        "corn-monopoly", "corn-monopoly-tiles", "corn-monopoly-hoard", "mcts", "random", "guided-random",
    };

    /// <summary>The strategy descriptions in the language of <paramref name="l"/>.</summary>
    public static IReadOnlyList<StrategyDoc> All(Loc l) => Ids.Select(id => Doc(l, id)).ToList();

    public static StrategyDoc Doc(Loc l, string id)
    {
        var rules = new List<string>();
        for (int i = 0; l.Has($"strat.{id}.rule.{i}"); i++) rules.Add(l.T($"strat.{id}.rule.{i}"));
        var parameters = new List<ParamInfo>();
        for (int i = 0; l.Has($"strat.{id}.p.{i}.name"); i++)
            parameters.Add(new ParamInfo(l.T($"strat.{id}.p.{i}.name"), l.T($"strat.{id}.p.{i}.default"),
                                         l.T($"strat.{id}.p.{i}.meaning"), l.T($"strat.{id}.p.{i}.range")));
        return new StrategyDoc(id, l.T($"strat.{id}.title"), l.T($"strat.{id}.summary"), rules.ToArray(), parameters.ToArray());
    }

    /// <summary>Tabs of the strategy descriptions: strategies grouped by their main good / plan.</summary>
    public sealed record StrategyGroup(string Key, string Title, string Hint, string[] Ids);

    private static readonly (string Key, string[] Ids)[] GroupIds =
    {
        ("corn", new[] { "corn-shipper", "corn-to-premium", "corn-monopoly", "corn-monopoly-tiles", "corn-monopoly-hoard" }),
        ("ship", new[] { "harbor-rush", "wharf-rush", "wharf-premium" }),
        ("build", new[] { "build-first", "cheap-engine" }),
        ("search", new[] { "mcts", "random", "guided-random" }),
    };

    public static IReadOnlyList<StrategyGroup> Groups(Loc l) =>
        GroupIds.Select(g => new StrategyGroup(g.Key, l.T($"strat.group.{g.Key}.title"), l.T($"strat.group.{g.Key}.hint"), g.Ids)).ToList();

    /// <summary>First tab key (for the page's default tab).</summary>
    public static string FirstGroupKey => GroupIds[0].Key;

    /// <summary>Strategies of a group in group order; a key that is not a group (e.g. "all") returns every strategy.</summary>
    public static IEnumerable<StrategyDoc> InGroup(Loc l, string key)
    {
        var g = GroupIds.FirstOrDefault(x => x.Key == key);
        return g.Ids == null ? All(l) : g.Ids.Select(id => Doc(l, id));
    }
}
