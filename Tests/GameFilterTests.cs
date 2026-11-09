using PuertoRico.Engine.Simulation;
using Xunit;

namespace PuertoRico.Tests;

public class GameFilterTests
{
    private static readonly Dictionary<string, string> Map = new() { ["a"] = "build-first", ["b"] = "corn-shipper" };

    private static GameRecord Game(int index, int rounds, int vpA, int vpB, string reason = "vpExhausted", List<int>? bldA = null, List<int>? roundsA = null) => new()
    {
        Index = index, Rounds = rounds, Decisions = rounds * 40, EndReason = reason,
        Winners = vpA >= vpB ? (vpA == vpB ? new List<int> { 0, 1 } : new List<int> { 0 }) : new List<int> { 1 },
        Players =
        {
            new PlayerRecord { Seat = 0, SeatId = "a", Vp = vpA, Rank = vpA >= vpB ? 1 : 2, Shipments = 10, Coins = 3, BonusPoints = 4, Buildings = bldA, BuiltRounds = roundsA, Tiles = new List<int> { 2, 0, 0, 0, 0, 1 } },
            new PlayerRecord { Seat = 1, SeatId = "b", Vp = vpB, Rank = vpB > vpA ? 1 : 2, Shipments = 4, Coins = 0, BonusPoints = 0, Buildings = new List<int>(), BuiltRounds = new List<int>(), Tiles = new List<int> { 5, 0, 0, 0, 0, 0 } },
        },
    };

    private static List<int> Matching(IEnumerable<GameRecord> games, GameFilter f) => games.Where(g => f.Matches(g, Map)).Select(g => g.Index).ToList();

    [Fact]
    public void Game_level_conditions()
    {
        var games = new[] { Game(0, 12, 40, 30), Game(1, 18, 35, 36, "cityFull"), Game(2, 15, 30, 30, "vpExhausted+colonistsShort") };
        Assert.Equal(new[] { 1, 2 }, Matching(games, new GameFilter { RoundsMin = 15 }));
        Assert.Equal(new[] { 2 }, Matching(games, new GameFilter { EndReason = "colonistsShort" }));
        Assert.Equal(new[] { 0, 2 }, Matching(games, new GameFilter { EndReason = "vpExhausted" }));
        Assert.Equal(new[] { 1, 2 }, Matching(games, new GameFilter { WinnerStrategy = "corn-shipper" })); // game 2 is a tie: both strategies won
        Assert.Equal(new[] { 2 }, Matching(games, new GameFilter { Tie = true }));
        Assert.Equal(new[] { 0 }, Matching(games, new GameFilter { MarginMin = 5 }));
        Assert.Equal(new[] { 1, 2 }, Matching(games, new GameFilter { MarginMax = 1 }));
        Assert.Equal(new[] { 1, 2 }, Matching(games, new GameFilter { WinnerSeat = 1 }));
    }

    [Fact]
    public void Margin_is_first_minus_second_and_zero_for_a_tie()
    {
        Assert.Equal(10, GameFilter.Margin(Game(0, 10, 40, 30)));
        Assert.Equal(0, GameFilter.Margin(Game(0, 10, 30, 30)));
    }

    [Fact]
    public void Player_conditions_must_hold_for_the_same_player()
    {
        var games = new[] { Game(0, 12, 40, 30) };
        // build-first scored 40 and shipped 10 times; corn-shipper scored 30 and shipped 4: no single player has score>=40 and shipments<=4
        var f = new GameFilter(); f.Player.ScoreMin = 40; f.Player.ShipmentsMax = 4;
        Assert.Empty(Matching(games, f));
        var g = new GameFilter(); g.Player.Strategy = "build-first"; g.Player.ScoreMin = 40; g.Player.ShipmentsMin = 10;
        Assert.Single(Matching(games, g));
        var tile = new GameFilter(); tile.Player.TileType = 0; tile.Player.TileMin = 5;
        Assert.Single(Matching(games, tile));
        var bonus = new GameFilter(); bonus.Player.Strategy = "corn-shipper"; bonus.Player.BonusMin = 1;
        Assert.Empty(Matching(games, bonus));
    }

    [Fact]
    public void Building_condition_with_round_limit_and_missing_records()
    {
        var games = new[] { Game(0, 12, 40, 30, bldA: new List<int> { 3, 7 }, roundsA: new List<int> { 2, 9 }), Game(1, 12, 40, 30) };
        var owns = new GameFilter(); owns.Player.Building = 7;
        Assert.Equal(new[] { 0 }, Matching(games, owns));
        var early = new GameFilter(); early.Player.Building = 7; early.Player.BuiltByRound = 5;
        Assert.Empty(Matching(games, early));
        var early2 = new GameFilter(); early2.Player.Building = 3; early2.Player.BuiltByRound = 5;
        Assert.Equal(new[] { 0 }, Matching(games, early2));
        Assert.True(owns.Player.NeedsBuildingRecords);
    }

    [Fact]
    public void Empty_filter_matches_everything()
    {
        var games = new[] { Game(0, 12, 40, 30), Game(1, 18, 35, 36) };
        Assert.Equal(2, Matching(games, new GameFilter()).Count);
    }
}
