using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.Mcts;

/// <summary>
/// Feature set version 2: every version-1 feature, unchanged and in the same order, followed by derived features the trees of
/// a version-1 model cannot easily build from the raw counts. All values are small integers (int16 in the dump).
/// <list type="bullet">
/// <item>Global: <c>picksLeft</c> (roles still to be chosen this round), <c>minCitySpacesLeft</c> (how close the nearest city is to
/// the end trigger), and <c>roleTakenRel{k}_{role}</c> (who took which role this round, seats relative to me: what is left for the
/// players still to choose).</item>
/// <item>Per seat (4 relative blocks, like version 1): what the seat could do with each role right now, which is what an opponent
/// is likely to pick: goods and production (Craftsman), barrels it could load (Captain), goods it could sell and at what best
/// price (Trader), buildings it could afford (Builder), plus building counts, unmanned large buildings and the city spaces left.</item>
/// </list>
/// </summary>
public static class FeaturesV2
{
    public const int Version = 2;
    private const int P = GameConstants.MaxPlayers;
    private const int G = GameConstants.GoodCount;
    private const int B = GameConstants.BuildingCount;
    private const int R = GameConstants.MaxRoleCount;

    private static readonly string[] SeatExtraNames =
    {
        "goodsTotal", "goodTypes", "productionTotal", "productionTypes", "shippable", "tradableGoods", "bestSalePrice",
        "affordableBuildings", "bestAffordableVp", "smallBuildings", "largeBuildings", "unfilledLarge", "citySpacesLeft",
    };

    private static readonly string[] GlobalExtraNames = BuildGlobalExtraNames();

    public static readonly string[] Names = BuildNames();
    public static int Count => Names.Length;

    /// <summary>The version-1 buffer is all this version needs.</summary>
    public static int ScratchLength => FeaturesV1.ScratchLength;

    private static string[] BuildGlobalExtraNames()
    {
        var n = new List<string> { "picksLeft", "minCitySpacesLeft" };
        for (int r = 0; r < R; r++)
            for (int k = 0; k < P; k++) n.Add($"roleTakenRel{k}_{(Role)r}");
        return n.ToArray();
    }

    private static string[] BuildNames()
    {
        var n = new List<string>(FeaturesV1.Names);
        n.AddRange(GlobalExtraNames);
        for (int r = 0; r < P; r++)
            foreach (var x in SeatExtraNames) n.Add($"p{r}_{x}");
        return n.ToArray();
    }

    public static void ExtractAll(GameState s, float[][] rows, float[] seatScratch)
    {
        FeaturesV1.ExtractAll(s, rows, seatScratch); // fills (and clears) the version-1 part of every row
        int players = s.PlayerCount, se = SeatExtraNames.Length, ge = GlobalExtraNames.Length, baseCount = FeaturesV1.Count;
        Span<float> seats = stackalloc float[P * se];
        seats.Clear();
        for (int seat = 0; seat < players; seat++) FillSeat(s, seat, seats.Slice(seat * se, se));
        for (int me = 0; me < players; me++)
        {
            var extra = rows[me].AsSpan(baseCount, Count - baseCount);
            extra.Clear();
            FillGlobal(s, me, extra[..ge]);
            for (int r = 0; r < players; r++)
                seats.Slice(((me + r) % players) * se, se).CopyTo(extra.Slice(ge + r * se, se));
        }
    }

    private static int Rel(int seat, int me, int players) => ((seat - me) % players + players) % players;

    private static void FillGlobal(GameState s, int me, Span<float> f)
    {
        int players = s.PlayerCount;
        int taken = 0;
        for (int r = 0; r < s.RoleCount && r < R; r++) if (s.RoleOwner[r] >= 0) taken++;
        f[0] = Math.Max(0, players - taken); // seats that have not chosen a role yet this round (the one being played counts as chosen)
        int min = int.MaxValue;
        for (int seat = 0; seat < players; seat++) min = Math.Min(min, GameConstants.CitySpaces - s.CitySpacesUsed(seat));
        f[1] = min;
        for (int r = 0; r < s.RoleCount && r < R; r++)
        {
            int owner = s.RoleOwner[r];
            if (owner >= 0) f[2 + r * P + Rel(owner, me, players)] = 1;
        }
    }

    private static void FillSeat(GameState s, int seat, Span<float> f)
    {
        int goodsTotal = 0, goodTypes = 0, productionTotal = 0, productionTypes = 0;
        for (int g = 0; g < G; g++)
        {
            int held = s.Goods[seat * G + g];
            goodsTotal += held;
            if (held > 0) goodTypes++;
            int made = Rules.ProductionOf(s, seat, g);
            productionTotal += made;
            if (made > 0) productionTypes++;
        }

        int tradable = 0, bestPrice = 0;
        if (s.TradeCount < GameConstants.TradeSlots)
        {
            bool office = s.HasOccupied(seat, BuildingId.Office);
            for (int g = 0; g < G; g++)
            {
                if (s.Goods[seat * G + g] <= 0 || (!office && InTradeHouse(s, g))) continue;
                tradable++;
                bestPrice = Math.Max(bestPrice, Rules.SalePrice(s, seat, g));
            }
        }

        int used = s.CitySpacesUsed(seat), spaceLeft = GameConstants.CitySpaces - used;
        int affordable = 0, bestVp = 0, small = 0, large = 0, unfilled = 0;
        for (int b = 0; b < B; b++)
        {
            if (s.BuildingOwned[seat * B + b] != 0)
            {
                if (Buildings.All[b].Large) { large++; if (s.BuildingOcc[seat * B + b] == 0) unfilled++; }
                else small++;
            }
            else if (s.BuildingSupply[b] > 0 && Buildings.Spaces[b] <= spaceLeft && Rules.BuildingCost(s, seat, b) <= s.Coins[seat])
            {
                affordable++;
                bestVp = Math.Max(bestVp, Buildings.Vp[b]);
            }
        }

        int i = 0;
        f[i++] = goodsTotal;
        f[i++] = goodTypes;
        f[i++] = productionTotal;
        f[i++] = productionTypes;
        f[i++] = Shippable(s, seat);
        f[i++] = tradable;
        f[i++] = bestPrice;
        f[i++] = affordable;
        f[i++] = bestVp;
        f[i++] = small;
        f[i++] = large;
        f[i++] = unfilled;
        f[i++] = spaceLeft;
    }

    private static bool InTradeHouse(GameState s, int good)
    {
        for (int i = 0; i < s.TradeCount; i++) if (s.TradeHouse[i] == good) return true;
        return false;
    }

    /// <summary>
    /// Barrels the seat could load in a Captain phase right now (rules.md section 4): a good already on a ship only goes to that ship,
    /// any other good needs an empty ship, and one ship carries one kind. The goods with the most barrels get the biggest empty
    /// ships (greedy). The Wharf is not counted.
    /// </summary>
    private static int Shippable(GameState s, int seat)
    {
        int total = 0;
        Span<int> rest = stackalloc int[G];
        int restCount = 0;
        for (int g = 0; g < G; g++)
        {
            int held = s.Goods[seat * G + g];
            if (held <= 0) continue;
            int holding = -1;
            for (int k = 0; k < GameConstants.ShipCount; k++)
                if (s.ShipLoad[k] > 0 && s.ShipGood[k] == g) { holding = k; break; }
            if (holding >= 0) total += Math.Min(held, Math.Max(0, s.ShipCap[holding] - s.ShipLoad[holding]));
            else rest[restCount++] = held;
        }
        Span<int> empty = stackalloc int[GameConstants.ShipCount];
        int emptyCount = 0;
        for (int k = 0; k < GameConstants.ShipCount; k++) if (s.ShipLoad[k] == 0) empty[emptyCount++] = s.ShipCap[k];
        SortDescending(rest[..restCount]);
        SortDescending(empty[..emptyCount]);
        for (int k = 0; k < Math.Min(restCount, emptyCount); k++) total += Math.Min(rest[k], empty[k]);
        return total;
    }

    private static void SortDescending(Span<int> a)
    {
        for (int i = 1; i < a.Length; i++)
        {
            int v = a[i], j = i - 1;
            while (j >= 0 && a[j] < v) { a[j + 1] = a[j]; j--; }
            a[j + 1] = v;
        }
    }
}
