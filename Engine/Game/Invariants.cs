namespace PuertoRico.Engine.Game;

/// <summary>Conservation and bounds checks used by tests and debugging. Returns null when the state is consistent.</summary>
public static class Invariants
{
    public static string? Check(GameState s)
    {
        const int P = GameConstants.Players, G = GameConstants.GoodCount, T = GameConstants.TileTypes, B = GameConstants.BuildingCount;

        int colonists = s.BankColonists + s.ShipColonists;
        for (int p = 0; p < P; p++) colonists += s.ColonistsOnBoard(p);
        if (colonists != GameConstants.TotalColonists) return $"colonists {colonists} != {GameConstants.TotalColonists}";

        for (int g = 0; g < G; g++)
        {
            int goods = s.GoodsSupply[g] + s.TradeHouse.Take(s.TradeCount).Count(x => x == g);
            for (int p = 0; p < P; p++) goods += s.Goods[p * G + g];
            for (int i = 0; i < GameConstants.ShipCount; i++) if (s.ShipGood[i] == g) goods += s.ShipLoad[i];
            if (goods != GameConstants.GoodsSupply[g]) return $"good {(Good)g}: {goods} != {GameConstants.GoodsSupply[g]}";

            int tiles = s.Deck[g] + s.Discard[g] + s.FaceUp[g];
            for (int p = 0; p < P; p++) tiles += s.Tiles[p * T + g];
            int expected = GameConstants.DeckStart[g] + (GameConstants.StartPlantation.Count(x => x == g));
            if (tiles != expected) return $"plantation {(Good)g}: {tiles} != {expected}";
        }

        int quarries = s.QuarrySupply;
        for (int p = 0; p < P; p++) quarries += s.Tiles[p * T + GameConstants.QuarryType];
        if (quarries != GameConstants.QuarryTotal) return $"quarries {quarries}";

        for (int b = 0; b < B; b++)
        {
            int n = s.BuildingSupply[b];
            for (int p = 0; p < P; p++) n += s.BuildingOwned[p * B + b];
            if (n != Buildings.Count[b]) return $"building {Buildings.All[b].Name}: {n} != {Buildings.Count[b]}";
        }

        int chips = s.VpSupply;
        for (int p = 0; p < P; p++) chips += s.VpChips[p];
        if (s.VpSupply > 0 && chips != GameConstants.VpChips) return $"vp chips {chips}";
        if (s.VpSupply < 0) return "negative vp supply";

        for (int p = 0; p < P; p++)
        {
            if (s.Coins[p] < 0) return $"seat {p} negative coins";
            if (s.TileCount(p) > GameConstants.MaxTiles) return $"seat {p} has {s.TileCount(p)} tiles";
            if (s.CitySpacesUsed(p) > GameConstants.CitySpaces) return $"seat {p} city overflow";
            for (int t = 0; t < T; t++)
                if (s.TilesOcc[p * T + t] > s.Tiles[p * T + t] || s.TilesOcc[p * T + t] < 0) return $"seat {p} tile occupancy";
            for (int b = 0; b < B; b++)
            {
                if (s.BuildingOcc[p * B + b] > 0 && s.BuildingOwned[p * B + b] == 0) return $"seat {p} colonist on unowned building";
                if (s.BuildingOcc[p * B + b] > Buildings.Capacity[b]) return $"seat {p} building over capacity";
            }
            if (s.SanJuan[p] < 0) return $"seat {p} negative San Juan";
        }
        for (int i = 0; i < GameConstants.ShipCount; i++)
            if (s.ShipLoad[i] > GameConstants.ShipCapacity[i]) return $"ship {i} overfull";
        if (s.TradeCount > GameConstants.TradeSlots) return "trading house overfull";
        return null;
    }
}
