using System.Text.Json;

namespace PuertoRico.Engine.Strategies.RuleBased;

/// <summary>
/// "Corn shipper": grow many corn plantations (they need no building), keep them manned, ship corn for VP every
/// Captain phase, and spend coins only on a short list of useful buildings (Hacienda, Harbor, Wharf, Hospice,
/// warehouses ...). All behaviour is the <see cref="HeuristicStrategy"/> default; <c>buildThreshold</c> defaults to 4.0 (tuned by a 4-player sweep, see sweeps/).
/// </summary>
public sealed class CornShipperStrategy : HeuristicStrategy
{
    public CornShipperStrategy(IReadOnlyDictionary<string, JsonElement> parameters) : base(parameters, 4.0) { }
}
