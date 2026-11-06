namespace PuertoRico.Engine.Game;

/// <summary>SplitMix64. The whole generator state is one ulong, so it copies with the game state.</summary>
public static class Rng
{
    public static ulong Next(ref ulong state)
    {
        state += 0x9E3779B97F4A7C15UL;
        ulong z = state;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
        return z ^ (z >> 31);
    }

    /// <summary>Uniform-enough integer in [0, n).</summary>
    public static int NextInt(ref ulong state, int n) =>
        (int)(((Next(ref state) >> 32) * (ulong)n) >> 32);

    /// <summary>One-shot mix of a value (used for seed derivation).</summary>
    public static ulong Mix(ulong value)
    {
        ulong s = value;
        return Next(ref s);
    }
}
