using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using PuertoRico.Engine.Strategies.Mcts;
using Xunit;

namespace PuertoRico.Tests;

/// <summary>
/// Version control (CLAUDE.md, section 版本與 hash): a golden-master test that fails when the engine's behaviour changed
/// without a new <see cref="EngineInfo.RulesRevision"/>, and a check that docs/versions.json lists the current numbers.
/// </summary>
public class GoldenTests
{
    private static string RepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "PuertoRico.sln"))) dir = dir.Parent;
        return dir?.FullName ?? throw new InvalidOperationException("PuertoRico.sln not found above " + AppContext.BaseDirectory);
    }

    private static SimulationConfig Cfg(string name, int players, int games, ulong seed, SeatOrderMode order, params string[] strategies) => new()
    {
        Name = name, Players = players, Games = games, Seed = seed, SeatOrder = order,
        Seats = strategies.Select((s, i) => new SeatConfig { Id = $"s{i}", Strategy = s }).ToList(),
    };

    /// <summary>Hand-written strategies and random players only: MCTS uses floating-point logs whose last digit may differ between platforms.</summary>
    private static readonly SimulationConfig[] Cases =
    {
        Cfg("3p-hand", 3, 120, 7001, SeatOrderMode.Balanced, "corn-shipper", "wharf-rush", "corn-monopoly"),
        Cfg("4p-hand", 4, 120, 7002, SeatOrderMode.Random, "cheap-engine", "build-first", "harbor-rush", "corn-to-premium"),
        Cfg("4p-premium", 4, 60, 7003, SeatOrderMode.Balanced, "wharf-premium", "corn-shipper", "build-first", "cheap-engine"),
        Cfg("4p-random", 4, 60, 7004, SeatOrderMode.Random, "random", "random", "guided-random", "guided-random"),
        Cfg("3p-guided", 3, 60, 7005, SeatOrderMode.Random, "guided-random", "guided-random", "build-first"),
    };

    /// <summary>SHA-256 over every game record (rounds, decisions, end reason, per-player scores, buildings, tiles, winners).</summary>
    private static string HashOf(SimulationConfig cfg)
    {
        using var sha = SHA256.Create();
        for (int g = 0; g < cfg.Games; g++)
        {
            var rec = GameRunner.Play(cfg, g);
            var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(rec, SimulationConfig.JsonOptions) + "\n");
            sha.TransformBlock(bytes, 0, bytes.Length, null, 0);
        }
        sha.TransformFinalBlock(Array.Empty<byte>(), 0, 0);
        return Convert.ToHexString(sha.Hash!).ToLowerInvariant();
    }

    [Fact]
    public void Engine_Behaviour_Matches_The_Golden_Hashes_Of_This_RulesRevision()
    {
        var current = Cases.ToDictionary(c => c.Name, HashOf);
        string path = Path.Combine(RepoRoot(), "Tests", "Data", "golden.json");
        if (Environment.GetEnvironmentVariable("PR_UPDATE_GOLDEN") == "1")
        {
            var doc = new { note = "Golden hashes of fixed games (Tests/VersionTests.cs). Regenerate with PR_UPDATE_GOLDEN=1 dotnet test --filter Golden, only together with a new EngineInfo.RulesRevision.", rulesRevision = EngineInfo.RulesRevision, cases = current };
            File.WriteAllText(path, JsonSerializer.Serialize(doc, new JsonSerializerOptions { WriteIndented = true }) + "\n");
            return;
        }
        using var golden = JsonDocument.Parse(File.ReadAllText(path));
        int recorded = golden.RootElement.GetProperty("rulesRevision").GetInt32();
        var changed = current.Where(kv => !golden.RootElement.GetProperty("cases").TryGetProperty(kv.Key, out var e) || e.GetString() != kv.Value)
                             .Select(kv => kv.Key).ToList();
        if (recorded == EngineInfo.RulesRevision)
            Assert.True(changed.Count == 0,
                $"The engine's behaviour changed ({string.Join(", ", changed)}) but EngineInfo.RulesRevision is still {EngineInfo.RulesRevision}.\n" +
                $"If the change is intended: set RulesRevision to {EngineInfo.RulesRevision + 1}, add an entry to docs/versions.json (rules track, and the engine track: at least a MINOR bump), " +
                "run PR_UPDATE_GOLDEN=1 dotnet test --filter Golden to refresh Tests/Data/golden.json, and tell the user which data and models are now stale. " +
                "If it was not intended, undo the change.");
        else
            Assert.True(recorded + 1 == EngineInfo.RulesRevision && changed.Count == 0,
                $"RulesRevision is {EngineInfo.RulesRevision} but Tests/Data/golden.json was recorded for {recorded} (or its hashes are out of date: {string.Join(", ", changed)}). " +
                "Run PR_UPDATE_GOLDEN=1 dotnet test --filter Golden.");
    }

    [Fact]
    public void Version_List_Names_The_Current_Version_Of_Every_Track()
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(RepoRoot(), "docs", "versions.json")));
        var latest = doc.RootElement.GetProperty("tracks").EnumerateArray().ToDictionary(
            t => t.GetProperty("id").GetString()!, t => t.GetProperty("entries")[0].GetProperty("version").GetString());
        Assert.Equal(EngineInfo.RulesRevision.ToString(), latest["rules"]);
        Assert.Equal(EngineInfo.Version, latest["engine"]);
        Assert.Equal(ValueFeatures.Version.ToString(), latest["features"]);
        Assert.Equal(PositionDump.FormatVersion.ToString(), latest["format"]);
        foreach (var track in doc.RootElement.GetProperty("tracks").EnumerateArray())
            foreach (var e in track.GetProperty("entries").EnumerateArray())
                Assert.True(e.GetProperty("changes").GetArrayLength() > 0, $"{track.GetProperty("id").GetString()} {e.GetProperty("version").GetString()}: no changes listed");
    }

    [Fact]
    public void Commit_Is_Known_Or_Unknown_But_Never_Empty()
    {
        Assert.False(string.IsNullOrWhiteSpace(EngineInfo.Commit));
    }
}
