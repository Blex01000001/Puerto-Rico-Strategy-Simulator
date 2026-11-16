using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;
using Xunit;

namespace PuertoRico.Tests;

public class EngineInfoTests
{
    [Fact]
    public void Version_And_RulesVersion_AreSet()
    {
        Assert.False(string.IsNullOrWhiteSpace(EngineInfo.Version));
        Assert.Equal("base", EngineInfo.RulesVersion);
        Assert.True(EngineInfo.RulesRevision >= 1);
    }

    [Fact]
    public void RulesRevision_IsWrittenIntoResultsAndDumps()
    {
        Assert.Equal(EngineInfo.RulesRevision, new SimulationResult().RulesRevision);
        var cfg = new SimulationConfig { Players = 3, Games = 2, Seed = 5, Seats = { new() { Id = "a", Strategy = "random" }, new() { Id = "b", Strategy = "random" }, new() { Id = "c", Strategy = "random" } } };
        string path = Path.Combine(Path.GetTempPath(), $"rev-{Guid.NewGuid():N}.bin");
        try
        {
            PositionDump.Run(cfg, path, 0.5);
            using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(path + ".json"));
            Assert.Equal(EngineInfo.RulesRevision, doc.RootElement.GetProperty("rulesRevision").GetInt32());
            Assert.Equal(2, doc.RootElement.GetProperty("requestedGames").GetInt32());
        }
        finally
        {
            File.Delete(path);
            File.Delete(path + ".json");
        }
    }
}
