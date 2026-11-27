using System.Globalization;
using System.Text;
using System.Text.Json;

namespace PuertoRico.Engine.Simulation;

/// <summary>
/// A result file as short Markdown to paste into a chat with an AI (Dashboard「複製摘要給 AI」; the ML UI has the same kind of text for its match records):
/// what was played, how long it took, the win shares with their 95% intervals and the versions. No per-game data, no machine paths.
/// The words come from the caller's text table (<paramref name="text"/> = key, arguments -&gt; text; the Dashboard passes its
/// <c>Loc.T</c>, the keys are <c>sum.*</c> in i18n/dash.&lt;language&gt;.json), so a new language needs no engine change.
/// Numbers are formatted here (invariant culture) and handed over as text.
/// </summary>
public static class ResultSummary
{
    /// <summary>Looks up a text by key and fills its placeholders {0}, {1}… with the arguments.</summary>
    public delegate string Text(string key, params object?[] args);

    public static string ToMarkdown(SimulationResult r, ResultAnalysis a, Text text)
    {
        var ci = CultureInfo.InvariantCulture;
        string sep = text("sum.sep");
        var cfg = r.Config;
        string P(double v) => (v * 100).ToString("0.0", ci) + "%";
        string N(long v) => v.ToString("N0", ci);
        var sb = new StringBuilder();
        sb.AppendLine(text("sum.title", string.IsNullOrWhiteSpace(cfg.Name) ? text("sum.unnamed") : cfg.Name));
        sb.AppendLine();
        sb.AppendLine(text("sum.games", cfg.Players, N(a.GamesCompleted), r.Status, N(r.GamesRequested), cfg.Seed.ToString(ci), cfg.SeatOrder));
        var seconds = r.FinishedUtc is { } f ? (f - r.StartedUtc).TotalSeconds : (double?)null;
        sb.AppendLine(text("sum.duration", Duration(seconds, text)) +
                      (seconds is > 0 && a.GamesCompleted > 0 ? text("sum.speed", (a.GamesCompleted / seconds.Value).ToString("0.00", ci)) : ""));
        // files written before resolvedSeats existed (engine < 0.3.0) get the current build's commit as the property default, which would be wrong
        string commit = r.ResolvedSeats != null ? Short(r.EngineCommit) : "—";
        sb.AppendLine(text("sum.engine", r.EngineVersion, commit, $"{r.RulesVersion}-v{r.RulesRevision}"));
        var revisions = (r.ResolvedSeats ?? new()).SelectMany(s => s.Revisions).GroupBy(kv => kv.Key).Select(g => $"{g.Key}-v{g.First().Value}").OrderBy(x => x, StringComparer.Ordinal).ToList();
        sb.AppendLine(text("sum.revisions", revisions.Count > 0 ? string.Join(sep, revisions) : "—"));
        sb.AppendLine();
        sb.AppendLine(text("sum.header"));
        sb.AppendLine("|---|---|---|---|---|---|---|");
        foreach (var s in a.Strategies)
        {
            var seat = cfg.Seats.FirstOrDefault(x => x.Id == s.SeatId);
            sb.AppendLine($"| {s.SeatId} | {s.Strategy} | {SeatParams(seat, text("sum.param_sep"))} | {P(s.WinShare)} | ±{P(s.WinShareCi95)} | {s.AvgScore.ToString("0.0", ci)} | {s.StdScore.ToString("0.0", ci)} |");
        }
        if (r.TableSeats.Count > 0)
            sb.AppendLine().AppendLine(text("sum.seats", string.Join(sep, r.TableSeats.OrderBy(t => t.Seat).Select(t => text("sum.seat", t.Seat + 1, P(t.WinShare))))));
        if (a.HasGameRecords)
            sb.AppendLine(text("sum.rounds", a.AvgRounds.ToString("0.0", ci), a.AvgDecisions.ToString("0", ci)));
        return sb.ToString().TrimEnd();
    }

    /// <summary>The parameters the config sets for the seat (valueModel shortened to its file name); "—" when it uses the defaults.</summary>
    private static string SeatParams(SeatConfig? seat, string sep)
    {
        if (seat == null || seat.Params.Count == 0) return "—";
        return string.Join(sep, seat.Params.Select(kv =>
        {
            string v = kv.Value.ValueKind == JsonValueKind.String ? kv.Value.GetString() ?? "" : kv.Value.GetRawText();
            if (kv.Key == "valueModel") v = v.Replace('\\', '/').Split('/').Last();
            return $"{kv.Key} {v}";
        }));
    }

    private static string Short(string? commit) => string.IsNullOrEmpty(commit) ? "—" : commit.Length > 7 ? commit[..7] : commit;

    private static string Duration(double? seconds, Text text)
    {
        if (seconds == null) return "—";
        int s = (int)Math.Round(seconds.Value);
        return s >= 3600 ? text("sum.dur_h", s / 3600, s % 3600 / 60) : s >= 60 ? text("sum.dur_m", s / 60, s % 60) : text("sum.dur_s", s);
    }
}
