using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.Mcts;

/// <summary>
/// Fixed-length numeric description of a game state from the point of view of one seat ("me"), used by the
/// learned value function (<see cref="IValueModel"/>) and by the position dump that produces its training data.
/// Player blocks are ordered relative to me (me, next seat, ...): 4 blocks, the 4th is all zero in 3-player games.
/// Every value is a small integer (the dump stores them as int16). Changing the list changes <see cref="Names"/>,
/// and models trained on the old list refuse to load (their feature names no longer match), so retrain after a change.
/// </summary>
public static class ValueFeatures
{
    private const int P = GameConstants.MaxPlayers;
    private const int G = GameConstants.GoodCount;
    private const int T = GameConstants.TileTypes;
    private const int B = GameConstants.BuildingCount;
    private const int R = GameConstants.MaxRoleCount;
    private const int Phases = (int)Phase.GameOver; // GameOver itself is never valued

    /// <summary>Version of the feature list (written to the dump metadata).</summary>
    public const int Version = 1;

    public static readonly string[] Names = BuildNames();
    public static int Count => Names.Length;
    private static readonly int GlobalCount = BuildGlobalNames().Count;
    private static readonly int SeatCount = BuildSeatNames("").Count;

    private static List<string> BuildGlobalNames()
    {
        var n = new List<string> { "players", "round", "endTriggered", "chosenCount" };
        for (int i = 0; i < Phases; i++) n.Add($"phase_{(Phase)i}");
        for (int i = 0; i < P; i++) n.Add($"actorRel{i}");
        for (int i = 0; i < P; i++) n.Add($"governorRel{i}");
        for (int i = 0; i < R; i++) n.Add($"currentRole_{(Role)i}");
        for (int i = 0; i < P; i++) n.Add($"currentOwnerRel{i}");
        n.AddRange(new[] { "vpSupply", "bankColonists", "shipColonists", "quarrySupply", "deckTotal", "tradeCount" });
        for (int g = 0; g < G; g++) n.Add($"goodsSupply_{(Good)g}");
        for (int g = 0; g < G; g++) n.Add($"faceUp_{(Good)g}");
        for (int g = 0; g < G; g++) n.Add($"tradeHouse_{(Good)g}");
        for (int b = 0; b < B; b++) n.Add($"buildingSupply_{(BuildingId)b}");
        for (int i = 0; i < R; i++) n.Add($"roleCoins_{(Role)i}");
        for (int i = 0; i < R; i++) n.Add($"roleAvailable_{(Role)i}");
        for (int k = 0; k < GameConstants.ShipCount; k++)
        {
            n.Add($"ship{k}_cap");
            n.Add($"ship{k}_load");
            for (int g = 0; g < G; g++) n.Add($"ship{k}_{(Good)g}");
        }
        return n;
    }

    private static List<string> BuildSeatNames(string prefix)
    {
        var n = new List<string>();
        foreach (var x in new[] { "present", "coins", "vpChips", "sanJuan", "colonists", "emptySlots", "citySpaces", "buildingVp", "bonusVp", "score", "tiebreak", "rank" })
            n.Add(prefix + x);
        for (int t = 0; t < T; t++) n.Add($"{prefix}tiles_{TileName(t)}");
        for (int t = 0; t < T; t++) n.Add($"{prefix}tilesOcc_{TileName(t)}");
        for (int g = 0; g < G; g++) n.Add($"{prefix}goods_{(Good)g}");
        for (int g = 0; g < G; g++) n.Add($"{prefix}production_{(Good)g}");
        for (int b = 0; b < B; b++) n.Add($"{prefix}owned_{(BuildingId)b}");
        for (int b = 0; b < B; b++) n.Add($"{prefix}occ_{(BuildingId)b}");
        return n;
    }

    private static string TileName(int t) => t == GameConstants.QuarryType ? "Quarry" : ((Good)t).ToString();

    private static string[] BuildNames()
    {
        var n = BuildGlobalNames();
        for (int r = 0; r < P; r++) n.AddRange(BuildSeatNames($"p{r}_"));
        return n.ToArray();
    }

    /// <summary>
    /// Fills one row per seat (rows[seat] = features from that seat's point of view; rows needs at least
    /// <c>s.PlayerCount</c> arrays of length <see cref="Count"/>). The per-seat blocks are computed once and shared.
    /// </summary>
    public static void ExtractAll(GameState s, float[][] rows, float[] seatScratch)
    {
        int players = s.PlayerCount;
        var score = Scoring.Score(s);
        for (int seat = 0; seat < players; seat++) FillSeat(s, seat, score.Players[seat], seatScratch.AsSpan(seat * SeatCount, SeatCount));
        for (int me = 0; me < players; me++)
        {
            var row = rows[me].AsSpan(0, Count);
            row.Clear();
            FillGlobal(s, me, row[..GlobalCount]);
            for (int r = 0; r < players; r++)
            {
                int seat = (me + r) % players;
                seatScratch.AsSpan(seat * SeatCount, SeatCount).CopyTo(row.Slice(GlobalCount + r * SeatCount, SeatCount));
            }
        }
    }

    /// <summary>Scratch buffer size for <see cref="ExtractAll"/>.</summary>
    public static int ScratchLength => P * SeatCount;

    /// <summary>Features of one seat (allocates; tests and tools only).</summary>
    public static float[] Extract(GameState s, int me)
    {
        var rows = new float[P][];
        for (int i = 0; i < P; i++) rows[i] = new float[Count];
        ExtractAll(s, rows, new float[ScratchLength]);
        return rows[me];
    }

    private static int Rel(int seat, int me, int players) => ((seat - me) % players + players) % players;

    private static void FillGlobal(GameState s, int me, Span<float> f)
    {
        int players = s.PlayerCount, i = 0;
        f[i++] = players;
        f[i++] = s.Round;
        f[i++] = s.EndFlags != EndFlags.None ? 1 : 0;
        f[i++] = s.ChosenCount;
        if ((int)s.Phase < Phases) f[i + (int)s.Phase] = 1;
        i += Phases;
        f[i + Rel(s.Actor, me, players)] = 1; i += P;
        f[i + Rel(s.Governor, me, players)] = 1; i += P;
        bool inRole = s.Phase != Phase.ChooseRole && s.Phase != Phase.GameOver;
        if (inRole) { f[i + s.CurrentRole] = 1; f[i + R + Rel(s.CurrentOwner, me, players)] = 1; }
        i += R + P;
        f[i++] = s.VpSupply;
        f[i++] = s.BankColonists;
        f[i++] = s.ShipColonists;
        f[i++] = s.QuarrySupply;
        f[i++] = s.DeckTotal();
        f[i++] = s.TradeCount;
        for (int g = 0; g < G; g++) f[i++] = s.GoodsSupply[g];
        for (int g = 0; g < G; g++) f[i++] = s.FaceUp[g];
        int tradeStart = i;
        i += G;
        for (int k = 0; k < s.TradeCount; k++) f[tradeStart + s.TradeHouse[k]]++;
        for (int b = 0; b < B; b++) f[i++] = s.BuildingSupply[b];
        for (int r = 0; r < R; r++) f[i++] = r < s.RoleCount ? s.RoleCoins[r] : 0;
        for (int r = 0; r < R; r++) f[i++] = r < s.RoleCount && s.RoleOwner[r] < 0 ? 1 : 0;
        for (int k = 0; k < GameConstants.ShipCount; k++)
        {
            f[i++] = s.ShipCap[k];
            f[i++] = s.ShipLoad[k];
            if (s.ShipLoad[k] > 0) f[i + s.ShipGood[k]] = 1;
            i += G;
        }
    }

    private static void FillSeat(GameState s, int seat, PlayerScore score, Span<float> f)
    {
        int i = 0, slots = 0, occ = 0;
        for (int b = 0; b < B; b++)
            if (s.BuildingOwned[seat * B + b] != 0) { slots += Buildings.Capacity[b]; occ += s.BuildingOcc[seat * B + b]; }
        int emptyTiles = 0;
        for (int t = 0; t < T; t++) emptyTiles += s.Tiles[seat * T + t] - s.TilesOcc[seat * T + t];
        f[i++] = 1;
        f[i++] = s.Coins[seat];
        f[i++] = s.VpChips[seat];
        f[i++] = s.SanJuan[seat];
        f[i++] = s.ColonistsOnBoard(seat);
        f[i++] = slots - occ + emptyTiles;
        f[i++] = s.CitySpacesUsed(seat);
        f[i++] = score.BuildingPoints;
        f[i++] = score.BonusPoints;
        f[i++] = score.Total;
        f[i++] = score.Tiebreak;
        f[i++] = score.Rank;
        for (int t = 0; t < T; t++) f[i++] = s.Tiles[seat * T + t];
        for (int t = 0; t < T; t++) f[i++] = s.TilesOcc[seat * T + t];
        for (int g = 0; g < G; g++) f[i++] = s.Goods[seat * G + g];
        for (int g = 0; g < G; g++) f[i++] = Rules.ProductionOf(s, seat, g);
        for (int b = 0; b < B; b++) f[i++] = s.BuildingOwned[seat * B + b];
        for (int b = 0; b < B; b++) f[i++] = s.BuildingOcc[seat * B + b];
    }
}
