namespace PuertoRico.Engine.Game;

public static class Setup
{
    /// <summary>
    /// New 3-player game (rules.md section 1). Seat 0 = Player 1 = starting governor. The random seed only
    /// drives plantation draws; seat/strategy assignment is a simulation-layer concern.
    /// </summary>
    public static GameState NewGame(ulong seed, int maxRounds = GameConstants.DefaultMaxRounds)
    {
        var s = new GameState { MaxRounds = maxRounds, RngState = seed };
        for (int seat = 0; seat < GameConstants.Players; seat++)
        {
            s.Coins[seat] = GameConstants.StartCoins;
            s.Tiles[seat * GameConstants.TileTypes + GameConstants.StartPlantation[seat]] = 1;
        }

        Array.Copy(GameConstants.GoodsSupply, s.GoodsSupply, GameConstants.GoodCount);
        for (int b = 0; b < GameConstants.BuildingCount; b++) s.BuildingSupply[b] = Buildings.Count[b];
        Array.Copy(GameConstants.DeckStart, s.Deck, GameConstants.GoodCount);
        s.QuarrySupply = GameConstants.QuarryTotal;
        s.BankColonists = GameConstants.BankColonists;
        s.ShipColonists = GameConstants.StartShipColonists;
        s.VpSupply = GameConstants.VpChips;
        Array.Fill(s.RoleOwner, -1);
        Array.Fill(s.ShipGood, -1);
        Array.Fill(s.TradeHouse, -1);

        Rules.FlipFaceUp(s);
        s.Phase = Phase.ChooseRole;
        s.Governor = 0;
        s.Actor = 0;
        s.Round = 1;
        return s;
    }
}
