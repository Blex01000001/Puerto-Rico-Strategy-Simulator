using PuertoRico.Engine.Game;
using Xunit;

namespace PuertoRico.Tests;

public class EngineInfoTests
{
    [Fact]
    public void Version_And_RulesVersion_AreSet()
    {
        Assert.False(string.IsNullOrWhiteSpace(EngineInfo.Version));
        Assert.Equal("base-3p", EngineInfo.RulesVersion);
    }
}
