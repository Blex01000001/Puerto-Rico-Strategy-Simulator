using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Simulation;

/// <summary>
/// All randomness derives from (master seed, game index, seat), never from threads or time, so the same
/// config reproduces the same results for any thread count.
/// </summary>
public static class SeedDeriver
{
    public static ulong GameSeed(ulong masterSeed, long gameIndex) =>
        Rng.Mix(Rng.Mix(masterSeed) + (ulong)gameIndex * 0x9E3779B97F4A7C15UL);

    public static ulong StrategySeed(ulong gameSeed, int configSeatIndex) =>
        Rng.Mix(gameSeed ^ (0xD1B54A32D192ED03UL * (ulong)(configSeatIndex + 1)));

    /// <summary>Seed for the seat permutation of <see cref="SeatOrderMode.Random"/>.</summary>
    public static ulong SeatSeed(ulong gameSeed) => Rng.Mix(gameSeed ^ 0xA0761D6478BD642FUL);
}
