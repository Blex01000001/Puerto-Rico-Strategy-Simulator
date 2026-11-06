namespace PuertoRico.Engine.Game;

public enum ActionType : byte
{
    /// <summary>A = role.</summary>
    ChooseRole,
    /// <summary>A = tile type (a face-up plantation of that good).</summary>
    TakePlantation,
    TakeQuarry,
    UseHacienda,
    Pass,
    /// <summary>A = slot: 0..4 plantation of that good, 5 quarry, 6+n building n.</summary>
    PlaceColonist,
    /// <summary>A = building id.</summary>
    Build,
    /// <summary>A = good (Craftsman privilege).</summary>
    CraftsmanBonus,
    /// <summary>A = good.</summary>
    Sell,
    /// <summary>A = good, B = public ship index.</summary>
    LoadShip,
    /// <summary>A = good.</summary>
    LoadWharf,
    /// <summary>A = good kept in full by a warehouse.</summary>
    KeepGoods,
    /// <summary>A = good for the single free barrel.</summary>
    KeepBarrel,
}

/// <summary>A decision. Small value type: no heap allocation, directly serialisable.</summary>
public readonly struct GameAction : IEquatable<GameAction>
{
    public readonly ActionType Type;
    public readonly byte A;
    public readonly byte B;

    public GameAction(ActionType type, int a = 0, int b = 0)
    {
        Type = type;
        A = (byte)a;
        B = (byte)b;
    }

    public static readonly GameAction Pass = new(ActionType.Pass);

    public bool Equals(GameAction other) => Type == other.Type && A == other.A && B == other.B;
    public override bool Equals(object? obj) => obj is GameAction o && Equals(o);
    public override int GetHashCode() => HashCode.Combine(Type, A, B);
    public static bool operator ==(GameAction l, GameAction r) => l.Equals(r);
    public static bool operator !=(GameAction l, GameAction r) => !l.Equals(r);

    public override string ToString() => Type switch
    {
        ActionType.ChooseRole => $"ChooseRole({(Role)A})",
        ActionType.TakePlantation => $"TakePlantation({(Good)A})",
        ActionType.PlaceColonist => A < GameConstants.TileTypes
            ? $"PlaceColonist({(A == GameConstants.QuarryType ? "Quarry" : ((Good)A).ToString() + " plantation")})"
            : $"PlaceColonist({Buildings.All[A - GameConstants.TileTypes].Name})",
        ActionType.Build => $"Build({Buildings.All[A].Name})",
        ActionType.CraftsmanBonus => $"CraftsmanBonus({(Good)A})",
        ActionType.Sell => $"Sell({(Good)A})",
        ActionType.LoadShip => $"LoadShip({(Good)A}, ship {B})",
        ActionType.LoadWharf => $"LoadWharf({(Good)A})",
        ActionType.KeepGoods => $"KeepGoods({(Good)A})",
        ActionType.KeepBarrel => $"KeepBarrel({(Good)A})",
        _ => Type.ToString(),
    };
}
