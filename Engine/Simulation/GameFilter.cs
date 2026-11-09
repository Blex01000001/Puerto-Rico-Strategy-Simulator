namespace PuertoRico.Engine.Simulation;

/// <summary>Conditions on one player of a game. All set conditions must hold for the same player.</summary>
public sealed class PlayerFilter
{
    public string? Strategy { get; set; }
    public int? Rank { get; set; }
    public int? ScoreMin { get; set; }
    public int? ScoreMax { get; set; }
    public int? ShipmentsMin { get; set; }
    public int? ShipmentsMax { get; set; }
    public int? CoinsMin { get; set; }
    public int? CoinsMax { get; set; }
    public int? BonusMin { get; set; }
    /// <summary>Building id the player must own (needs per-building records).</summary>
    public int? Building { get; set; }
    /// <summary>With <see cref="Building"/>: bought in this round or earlier.</summary>
    public int? BuiltByRound { get; set; }
    /// <summary>Tile type index 0..5 (corn, indigo, sugar, tobacco, coffee, quarry) and the minimum count.</summary>
    public int? TileType { get; set; }
    public int? TileMin { get; set; }

    public bool IsActive => Strategy != null || Rank != null || ScoreMin != null || ScoreMax != null || ShipmentsMin != null || ShipmentsMax != null
        || CoinsMin != null || CoinsMax != null || BonusMin != null || Building != null || (TileType != null && TileMin != null);

    /// <summary>True when the condition needs data that older result files lack (building list, final tiles).</summary>
    public bool NeedsBuildingRecords => Building != null || (TileType != null && TileMin != null);

    public bool Matches(PlayerRecord p, IReadOnlyDictionary<string, string> strategyBySeatId)
    {
        if (Strategy != null && !(strategyBySeatId.TryGetValue(p.SeatId, out var s) && s == Strategy)) return false;
        if (Rank != null && p.Rank != Rank) return false;
        if (ScoreMin != null && p.Vp < ScoreMin) return false;
        if (ScoreMax != null && p.Vp > ScoreMax) return false;
        if (ShipmentsMin != null && p.Shipments < ShipmentsMin) return false;
        if (ShipmentsMax != null && p.Shipments > ShipmentsMax) return false;
        if (CoinsMin != null && p.Coins < CoinsMin) return false;
        if (CoinsMax != null && p.Coins > CoinsMax) return false;
        if (BonusMin != null && p.BonusPoints < BonusMin) return false;
        if (Building != null)
        {
            if (p.Buildings == null) return false;
            int i = p.Buildings.IndexOf(Building.Value);
            if (i < 0) return false;
            if (BuiltByRound != null && (p.BuiltRounds == null || p.BuiltRounds[i] > BuiltByRound)) return false;
        }
        if (TileType != null && TileMin != null)
        {
            if (p.Tiles == null || TileType < 0 || TileType >= p.Tiles.Count || p.Tiles[TileType.Value] < TileMin) return false;
        }
        return true;
    }
}

/// <summary>Conditions for the game list of the results page; every set condition must hold (AND).</summary>
public sealed class GameFilter
{
    public int? RoundsMin { get; set; }
    public int? RoundsMax { get; set; }
    public int? DecisionsMin { get; set; }
    public int? DecisionsMax { get; set; }
    /// <summary>One end-reason flag, e.g. <c>vpExhausted</c>; games whose reason contains it match.</summary>
    public string? EndReason { get; set; }
    /// <summary>Strategy name of a winner.</summary>
    public string? WinnerStrategy { get; set; }
    /// <summary>Table seat (0-based) of a winner.</summary>
    public int? WinnerSeat { get; set; }
    /// <summary>true = only full ties for first place, false = only games with a single winner, null = both.</summary>
    public bool? Tie { get; set; }
    /// <summary>Points between first and second place (0 for a tie).</summary>
    public int? MarginMin { get; set; }
    public int? MarginMax { get; set; }
    public PlayerFilter Player { get; } = new();

    public static int Margin(GameRecord g)
    {
        if (g.Players.Count < 2) return 0;
        var scores = g.Players.Select(p => p.Vp).OrderByDescending(v => v).ToList();
        return scores[0] - scores[1];
    }

    public bool Matches(GameRecord g, IReadOnlyDictionary<string, string> strategyBySeatId)
    {
        if (RoundsMin != null && g.Rounds < RoundsMin) return false;
        if (RoundsMax != null && g.Rounds > RoundsMax) return false;
        if (DecisionsMin != null && g.Decisions < DecisionsMin) return false;
        if (DecisionsMax != null && g.Decisions > DecisionsMax) return false;
        if (!string.IsNullOrEmpty(EndReason) && !g.EndReason.Split('+').Contains(EndReason)) return false;
        if (WinnerStrategy != null && !g.Winners.Any(w => WinnerStrategyOf(g, w, strategyBySeatId) == WinnerStrategy)) return false;
        if (WinnerSeat != null && !g.Winners.Contains(WinnerSeat.Value)) return false;
        if (Tie != null && (g.Winners.Count > 1) != Tie) return false;
        if (MarginMin != null || MarginMax != null)
        {
            int m = Margin(g);
            if (MarginMin != null && m < MarginMin) return false;
            if (MarginMax != null && m > MarginMax) return false;
        }
        if (Player.IsActive && !g.Players.Any(p => Player.Matches(p, strategyBySeatId))) return false;
        return true;
    }

    private static string? WinnerStrategyOf(GameRecord g, int seat, IReadOnlyDictionary<string, string> map)
    {
        var p = g.Players.FirstOrDefault(x => x.Seat == seat);
        return p != null && map.TryGetValue(p.SeatId, out var s) ? s : null;
    }

    /// <summary>Strategy name per config seat id (what the filters compare against).</summary>
    public static Dictionary<string, string> StrategyMap(SimulationConfig cfg) =>
        cfg.Seats.ToDictionary(s => s.Id, s => s.Strategy);
}
