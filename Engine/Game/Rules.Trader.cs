namespace PuertoRico.Engine.Game;

public static partial class Rules
{
    // rules.md section 4 (Trader)

    public static int SalePrice(GameState s, int seat, int good)
    {
        int price = GameConstants.BasePrice[good];
        if (s.HasOccupied(seat, BuildingId.SmallMarket)) price += 1;
        if (s.HasOccupied(seat, BuildingId.LargeMarket)) price += 2;
        if (seat == s.CurrentOwner) price += 1;
        return price;
    }

    private static bool InTradeHouse(GameState s, int good)
    {
        for (int i = 0; i < s.TradeCount; i++) if (s.TradeHouse[i] == good) return true;
        return false;
    }

    private static void FillTrader(GameState s, List<GameAction> a)
    {
        if (s.TradeCount >= GameConstants.TradeSlots) return;
        int p = s.Actor;
        bool office = s.HasOccupied(p, BuildingId.Office);
        bool any = false;
        for (int g = 0; g < G; g++)
        {
            if (s.Goods[p * G + g] <= 0) continue;
            if (!office && InTradeHouse(s, g)) continue;
            if (!any) { a.Add(GameAction.Pass); any = true; }
            a.Add(new GameAction(ActionType.Sell, g));
        }
    }

    private static void ApplyTrader(GameState s, GameAction a)
    {
        int p = s.Actor;
        if (a.Type == ActionType.Pass) { NextActor(s); return; }
        if (a.Type != ActionType.Sell) throw new InvalidOperationException($"{a} is not a Trader action");

        int g = a.A;
        s.Coins[p] += SalePrice(s, p, g);
        s.Goods[p * G + g]--;
        s.TradeHouse[s.TradeCount++] = g;
        NextActor(s);
    }

    /// <summary>The trading house is emptied at the end of the phase only if all four slots are full.</summary>
    private static void ClearTradeHouseIfFull(GameState s)
    {
        if (s.TradeCount < GameConstants.TradeSlots) return;
        for (int i = 0; i < s.TradeCount; i++)
        {
            s.GoodsSupply[s.TradeHouse[i]]++;
            s.TradeHouse[i] = -1;
        }
        s.TradeCount = 0;
    }
}
