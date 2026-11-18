using PuertoRico.Engine.Simulation;
using Xunit;

namespace PuertoRico.Tests;

public class ResultFilesTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "pr-resultfiles-" + Guid.NewGuid().ToString("N"));

    public ResultFilesTests() => Directory.CreateDirectory(_dir);

    public void Dispose() => Directory.Delete(_dir, recursive: true);

    private void Touch(string relative)
    {
        string path = Path.Combine(_dir, relative);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "{}");
    }

    [Fact]
    public void Lists_Results_And_The_Ml_Folder_But_Not_Dump_Metadata_Temp_Files_Or_Other_Folders()
    {
        Touch("a.json");
        Touch("b.json.tmp");
        Touch("ml/4p-v3-vs-v2.json");     // the ML UI's match result
        Touch("ml/4p-hand-a.bin.json");   // dump metadata: not a result
        Touch("ml/jobs/20260101-aaaaaa/job.json");
        Touch(".presets/overview-presets.json");
        var files = ResultFiles.List(_dir);
        Assert.Equal(new[] { "a.json", "ml/4p-v3-vs-v2.json" }, files.Select(f => ResultFiles.Label(_dir, f)).ToArray());
    }

    [Fact]
    public void A_Missing_Folder_Gives_An_Empty_List() => Assert.Empty(ResultFiles.List(Path.Combine(_dir, "nope")));
}
