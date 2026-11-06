namespace PuertoRico.Engine.Game;

public static class Setup
{
    /// <summary>
    /// New game for 3 or 4 players (rules.md sections 1 and 7). Seat 0 = Player 1 = starting governor. The random seed only
    /// drives plantation draws; seat/strategy assignment is a simulation-layer concern.
    /// </summary>
    public static GameState NewGame(ulong seed, int maxRounds = GameConstants.DefaultMaxRounds, int players = 3)
    {
        if (players < GameConstants.MinPlayers || players > GameConstants.MaxPlayers)
            throw new ArgumentOutOfRangeException(nameof(players), "3 or 4 players");

        var s = new GameState { PlayerCount = players, MaxRounds = maxRounds, RngState = seed };
        var start = GameConstants.StartPlantation(players);
        for (int seat = 0; seat < players; seat++)
        {
            s.Coins[seat] = GameConstants.StartCoins(players);
            s.Tiles[seat * GameConstants.TileTypes + start[seat]] = 1;
        }

        Array.Copy(GameConstants.ShipCapacity(players), s.ShipCap, GameConstants.ShipCount);
        Array.Copy(GameConstants.GoodsSupply, s.GoodsSupply, GameConstants.GoodCount);
        for (int b = 0; b < GameConstants.BuildingCount; b++) s.BuildingSupply[b] = Buildings.Count[b];
        Array.Copy(GameConstants.DeckStart(players), s.Deck, GameConstants.GoodCount);
        s.QuarrySupply = GameConstants.QuarryTotal;
        s.ColonistTotal = GameConstants.TotalColonists(players);
        s.BankColonists = GameConstants.BankColonists(players);
        s.ShipColonists = GameConstants.StartShipColonists(players);
        s.VpChipTotal = GameConstants.VpChips(players);
        s.VpSupply = s.VpChipTotal;
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
