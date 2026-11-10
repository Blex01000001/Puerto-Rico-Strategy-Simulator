using PuertoRico.Engine.Game;

namespace Dashboard.Services;

/// <summary>Chinese description of one decision, computed from the state before it (who pays what, how much a sale brings…).</summary>
public static class ActionText
{
    public static readonly string[] Goods = { "玉米", "靛藍", "糖", "菸草", "咖啡" };
    public static readonly string[] Roles = { "開拓者", "市長", "建築師", "工匠", "商人", "船長", "淘金者" };
    public static string GoodName(int g) => g >= 0 && g < Goods.Length ? Goods[g] : "?";
    public static string RoleName(int r) => r >= 0 && r < Roles.Length ? Roles[r] : "?";

    public static string Describe(GameState s, GameAction a)
    {
        int p = s.Actor;
        switch (a.Type)
        {
            case ActionType.ChooseRole:
            {
                int coins = s.RoleCoins[a.A];
                return $"選擇職業「{RoleName(a.A)}」" + (coins > 0 ? $"（拿走職業上的 {coins} 金幣）" : "");
            }
            case ActionType.TakePlantation: return $"拿走翻開的「{GoodName(a.A)}」種植園";
            case ActionType.TakeQuarry: return "拿採石場";
            case ActionType.UseHacienda: return "使用 Hacienda：從牌堆盲抽一張種植園";
            case ActionType.Pass: return PassText(s);
            case ActionType.PlaceColonist:
                return a.A < GameConstants.TileTypes
                    ? $"派殖民者到{(a.A == GameConstants.QuarryType ? "採石場" : GoodName(a.A) + "種植園")}"
                    : $"派殖民者到建築 {Buildings.All[a.A - GameConstants.TileTypes].Name}";
            case ActionType.Build:
            {
                var info = Buildings.All[a.A];
                int cost = Rules.BuildingCost(s, p, a.A);
                return $"建造 {info.Name}：付 {cost} 金幣" + (cost != info.Cost ? $"（原價 {info.Cost}，有折扣）" : "") + $"，建築 {info.Vp} 分" + (info.Large ? "（大型建築）" : "");
            }
            case ActionType.CraftsmanBonus: return $"工匠特權：額外拿 1 個{GoodName(a.A)}";
            case ActionType.Sell: return $"賣出 1 個{GoodName(a.A)}到交易所，得 {Rules.SalePrice(s, p, a.A)} 金幣";
            case ActionType.LoadShip:
            {
                int amount = Math.Min(s.Goods[p * GameConstants.GoodCount + a.A], s.ShipCap[a.B] - s.ShipLoad[a.B]);
                int vp = amount + (s.HasOccupied(p, BuildingId.Harbor) ? 1 : 0) + (p == s.CurrentOwner && s.CaptainFirstDone == 0 ? 1 : 0);
                return $"把 {amount} 個{GoodName(a.A)}裝上 {s.ShipCap[a.B]} 格貨船，得 {vp} 分";
            }
            case ActionType.LoadWharf:
            {
                int amount = s.Goods[p * GameConstants.GoodCount + a.A];
                int vp = amount + (s.HasOccupied(p, BuildingId.Harbor) ? 1 : 0) + (p == s.CurrentOwner && s.CaptainFirstDone == 0 ? 1 : 0);
                return $"用 Wharf 出貨 {amount} 個{GoodName(a.A)}，得 {vp} 分";
            }
            case ActionType.KeepGoods: return $"倉庫保留所有{GoodName(a.A)}";
            case ActionType.KeepBarrel: return $"保留 1 桶{GoodName(a.A)}";
            default: return a.ToString();
        }
    }

    /// <summary>Description of every action of a search summary, in the same order.</summary>
    public static IReadOnlyList<string> DescribeAll(GameState s, PuertoRico.Engine.Strategies.SearchSummary search) =>
        search.Actions.Select(e => Describe(s, e.Action)).ToList();

    /// <summary>
    /// Principal variation of every action of a search summary as text ("座位 2：… → 座位 3：…"). The steps are replayed
    /// on a copy of the state (plantation draws may differ from the real game); a step that is no longer legal ends the line.
    /// </summary>
    public static IReadOnlyList<string> DescribeLines(GameState s, PuertoRico.Engine.Strategies.SearchSummary search)
    {
        var result = new List<string>(search.Actions.Count);
        var legal = new List<GameAction>(32);
        foreach (var e in search.Actions)
        {
            var parts = new List<string>();
            if (e.Line is { Count: > 0 })
            {
                var c = s.Clone();
                PuertoRico.Engine.Game.Rules.Apply(c, e.Action);
                foreach (var step in e.Line)
                {
                    if (c.IsOver) break;
                    PuertoRico.Engine.Game.Rules.GetLegalActions(c, legal);
                    if (c.Actor != step.Seat || !legal.Contains(step.Action)) break;
                    parts.Add($"座位 {step.Seat + 1}：{Describe(c, step.Action)}");
                    PuertoRico.Engine.Game.Rules.Apply(c, step.Action);
                }
            }
            result.Add(string.Join(" → ", parts));
        }
        return result;
    }

    private static string PassText(GameState s) => s.Phase switch
    {
        Phase.Settler => "不拿種植園（跳過）",
        Phase.Builder => "不建造（跳過）",
        Phase.Trader => "不賣貨（跳過）",
        Phase.Captain => "無法／不再出貨（跳過）",
        Phase.Mayor => "跳過",
        _ => "跳過",
    };
}
