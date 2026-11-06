namespace PuertoRico.Engine.Game;

public sealed record PlayerScore(int Seat, int Chips, int BuildingPoints, int BonusPoints, int Total, int Tiebreak, int Rank);

public sealed record GameScore(PlayerScore[] Players, int[] Winners);

/// <summary>Final scoring (rules.md section 5).</summary>
public static class Scoring
{
    private const int B = GameConstants.BuildingCount;

    /// <summary>
    /// If true, Guild Hall / City Hall only count buildings that hold a colonist. rules.md says only the
    /// large building itself needs a colonist, so this is false (see docs/TODO.md).
    /// </summary>
    public const bool CountedBuildingsNeedColonist = false;

    public static GameScore Score(GameState s)
    {
        int players = s.PlayerCount;
        var rows = new (int Seat, int Chips, int Building, int Bonus, int Total, int Tie)[players];
        for (int p = 0; p < players; p++)
        {
            int chips = s.VpChips[p];
            int building = 0;
            for (int b = 0; b < B; b++) if (s.BuildingOwned[p * B + b] != 0) building += Buildings.Vp[b];
            int bonus = LargeBuildingBonus(s, p);
            int total = chips + building + bonus;
            int tie = s.Coins[p] + s.GoodTotal(p);
            rows[p] = (p, chips, building, bonus, total, tie);
        }

        int bestTotal = rows.Max(r => r.Total);
        int bestTie = rows.Where(r => r.Total == bestTotal).Max(r => r.Tie);
        var winners = rows.Where(r => r.Total == bestTotal && r.Tie == bestTie).Select(r => r.Seat).ToArray();

        var scores = new PlayerScore[players];
        foreach (var r in rows)
        {
            // Rank = 1 + number of players strictly ahead (by total, then tiebreak).
            int rank = 1 + rows.Count(o => o.Total > r.Total || (o.Total == r.Total && o.Tie > r.Tie));
            scores[r.Seat] = new PlayerScore(r.Seat, r.Chips, r.Building, r.Bonus, r.Total, r.Tie, rank);
        }
        return new GameScore(scores, winners);
    }

    private static bool Counts(GameState s, int seat, int b) =>
        s.BuildingOwned[seat * B + b] != 0 && (!CountedBuildingsNeedColonist || s.BuildingOcc[seat * B + b] > 0);

    private static int LargeBuildingBonus(GameState s, int p)
    {
        int bonus = 0;
        if (s.HasOccupied(p, BuildingId.GuildHall))
        {
            for (int b = 0; b < B; b++)
            {
                if (!Counts(s, p, b) || !Buildings.All[b].IsProduction) continue;
                bonus += Buildings.All[b].Tier == 1 ? 1 : 2; // small (tier 1) = 1 VP, large production = 2 VP
            }
        }
        if (s.HasOccupied(p, BuildingId.Residence))
        {
            int tiles = s.TileCount(p);
            bonus += tiles <= 9 ? 4 : tiles - 5; // 10 -> 5, 11 -> 6, 12 -> 7
        }
        if (s.HasOccupied(p, BuildingId.Fortress)) bonus += s.ColonistsOnBoard(p) / 3;
        if (s.HasOccupied(p, BuildingId.CustomsHouse)) bonus += s.VpChips[p] / 4;
        if (s.HasOccupied(p, BuildingId.CityHall))
        {
            for (int b = 0; b < B; b++)
                if (Counts(s, p, b) && Buildings.All[b].IsViolet) bonus++;
        }
        return bonus;
    }
}
