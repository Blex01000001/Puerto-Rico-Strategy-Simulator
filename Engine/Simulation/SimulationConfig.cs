using System.Text.Json;
using System.Text.Json.Serialization;

namespace PuertoRico.Engine.Simulation;

public enum SeatOrderMode
{
    /// <summary>Config seat i always sits at table seat i.</summary>
    Fixed,
    /// <summary>Strategies rotate through the table seats game by game (default; removes the seat advantage).</summary>
    Rotate,
    /// <summary>Random permutation per game (derived from the game seed).</summary>
    Random,
}

public sealed class SeatConfig
{
    public string Id { get; set; } = "";
    public string Strategy { get; set; } = "random";
    public Dictionary<string, JsonElement> Params { get; set; } = new();
}

public sealed class LimitsConfig
{
    public int MaxRounds { get; set; } = 150;
    public int MaxDecisionsPerGame { get; set; } = 20000;
}

public sealed class OptionsConfig
{
    /// <summary>Apply a decision directly when it has exactly one legal action instead of asking the strategy.</summary>
    public bool AutoAdvanceForced { get; set; } = true;
    public bool EventLog { get; set; } = false;
}

public sealed class OutputConfig
{
    /// <summary>Write every game into the result file (needed for --resume).</summary>
    public bool PerGameRecords { get; set; } = true;
    public int CheckpointEverySeconds { get; set; } = 60;
    public int CheckpointEveryGames { get; set; } = 5000;
}

public sealed class ParallelismConfig
{
    /// <summary>0 = all cores.</summary>
    public int MaxDegree { get; set; } = 0;
}

/// <summary>Simulation settings shared by the Runner and the Dashboard (JSON, camelCase).</summary>
public sealed class SimulationConfig
{
    public int SchemaVersion { get; set; } = 1;
    public string Name { get; set; } = "";
    public int Players { get; set; } = 3;
    public int Games { get; set; } = 1000;
    public ulong Seed { get; set; } = 12345;
    public SeatOrderMode SeatOrder { get; set; } = SeatOrderMode.Rotate;
    public List<SeatConfig> Seats { get; set; } = new()
    {
        new SeatConfig { Id = "A", Strategy = "random" },
        new SeatConfig { Id = "B", Strategy = "random" },
        new SeatConfig { Id = "C", Strategy = "random" },
    };
    public LimitsConfig Limits { get; set; } = new();
    public OptionsConfig Options { get; set; } = new();
    public OutputConfig Output { get; set; } = new();
    public ParallelismConfig Parallelism { get; set; } = new();

    public static readonly JsonSerializerOptions JsonOptions = CreateJsonOptions();

    private static JsonSerializerOptions CreateJsonOptions()
    {
        var o = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            PropertyNameCaseInsensitive = true,
            WriteIndented = false,
            ReadCommentHandling = JsonCommentHandling.Skip,
            AllowTrailingCommas = true,
        };
        o.Converters.Add(new JsonStringEnumConverter(JsonNamingPolicy.CamelCase));
        return o;
    }

    public static SimulationConfig Load(string path) =>
        JsonSerializer.Deserialize<SimulationConfig>(File.ReadAllText(path), JsonOptions)
        ?? throw new InvalidDataException($"Empty config: {path}");

    public void Validate()
    {
        if (Players != 3) throw new InvalidDataException("Only 3-player games are supported.");
        if (Seats.Count != Players) throw new InvalidDataException($"Expected {Players} seats, got {Seats.Count}.");
        if (Games < 0) throw new InvalidDataException("games must be >= 0");
        if (Seats.Select(s => s.Id).Distinct().Count() != Seats.Count || Seats.Any(s => string.IsNullOrWhiteSpace(s.Id)))
            throw new InvalidDataException("Seat ids must be unique and non-empty.");
        foreach (var seat in Seats)
            if (!Strategies.StrategyRegistry.IsKnown(seat.Strategy))
                throw new InvalidDataException($"Unknown strategy '{seat.Strategy}' for seat '{seat.Id}'.");
    }
}
