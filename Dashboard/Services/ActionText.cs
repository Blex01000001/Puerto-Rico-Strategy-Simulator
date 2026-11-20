using PuertoRico.Engine.Game;

namespace Dashboard.Services;

/// <summary>Description of one decision in the language of a <see cref="Loc"/>, computed from the state before it (who pays what, how much a sale brings…).</summary>
public static class ActionText
{
    public static string GoodName(Loc l, int g) => g >= 0 && g < GameConstants.GoodCount ? l.T("good." + g) : "?";
    public static string RoleName(Loc l, int r) => r >= 0 && r < 7 ? l.T("role." + r) : "?";

    public static string Describe(Loc l, GameState s, GameAction a)
    {
        int p = s.Actor;
        switch (a.Type)
        {
            case ActionType.ChooseRole:
            {
                int coins = s.RoleCoins[a.A];
                return l.T("act.choose_role", RoleName(l, a.A)) + (coins > 0 ? l.T("act.role_coins", coins) : "");
            }
            case ActionType.TakePlantation: return l.T("act.take_plantation", GoodName(l, a.A));
            case ActionType.TakeQuarry: return l.T("act.take_quarry");
            case ActionType.UseHacienda: return l.T("act.hacienda");
            case ActionType.Pass: return PassText(l, s);
            case ActionType.PlaceColonist:
                return a.A < GameConstants.TileTypes
                    ? l.T("act.place", a.A == GameConstants.QuarryType ? l.T("act.target.quarry") : l.T("act.target.plantation", GoodName(l, a.A)))
                    : l.T("act.place_building", Buildings.All[a.A - GameConstants.TileTypes].Name);
            case ActionType.Build:
            {
                var info = Buildings.All[a.A];
                int cost = Rules.BuildingCost(s, p, a.A);
                return l.T("act.build", info.Name, cost) + (cost != info.Cost ? l.T("act.build_discount", info.Cost) : "") + l.T("act.build_vp", info.Vp) + (info.Large ? l.T("act.build_large") : "");
            }
            case ActionType.CraftsmanBonus: return l.T("act.craftsman", GoodName(l, a.A));
            case ActionType.Sell: return l.T("act.sell", GoodName(l, a.A), Rules.SalePrice(s, p, a.A));
            case ActionType.LoadShip:
            {
                int amount = Math.Min(s.Goods[p * GameConstants.GoodCount + a.A], s.ShipCap[a.B] - s.ShipLoad[a.B]);
                int vp = amount + (s.HasOccupied(p, BuildingId.Harbor) ? 1 : 0) + (p == s.CurrentOwner && s.CaptainFirstDone == 0 ? 1 : 0);
                return l.T("act.load", amount, GoodName(l, a.A), s.ShipCap[a.B], vp);
            }
            case ActionType.LoadWharf:
            {
                int amount = s.Goods[p * GameConstants.GoodCount + a.A];
                int vp = amount + (s.HasOccupied(p, BuildingId.Harbor) ? 1 : 0) + (p == s.CurrentOwner && s.CaptainFirstDone == 0 ? 1 : 0);
                return l.T("act.wharf", amount, GoodName(l, a.A), vp);
            }
            case ActionType.KeepGoods: return l.T("act.keep_goods", GoodName(l, a.A));
            case ActionType.KeepBarrel: return l.T("act.keep_barrel", GoodName(l, a.A));
            default: return a.ToString();
        }
    }

    /// <summary>Description of every action of a search summary, in the same order.</summary>
    public static IReadOnlyList<string> DescribeAll(Loc l, GameState s, PuertoRico.Engine.Strategies.SearchSummary search) =>
        search.Actions.Select(e => Describe(l, s, e.Action)).ToList();

    private static string PassText(Loc l, GameState s) => s.Phase switch
    {
        Phase.Settler => l.T("act.pass.settler"),
        Phase.Builder => l.T("act.pass.builder"),
        Phase.Trader => l.T("act.pass.trader"),
        Phase.CraftsmanBonus => l.T("act.pass.craftsman"),
        Phase.CaptainStorage => l.T(s.StoreKeptCount < s.StoreTarget ? "act.pass.store_kinds" : "act.pass.store_barrel"),
        Phase.Captain => l.T("act.pass.captain"),
        _ => l.T("act.pass.other"),
    };
}
