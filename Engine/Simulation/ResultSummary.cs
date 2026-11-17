using System.Globalization;
using System.Text;
using System.Text.Json;

namespace PuertoRico.Engine.Simulation;

/// <summary>
/// A result file as short Markdown to paste into a chat with an AI (Dashboard「複製摘要給 AI」; the ML UI has the same kind of text for its match records):
/// what was played, how long it took, the win shares with their 95% intervals and the versions. No per-game data, no machine paths.
/// </summary>
public static class ResultSummary
{
    public static string ToMarkdown(SimulationResult r, ResultAnalysis a)
    {
        var ci = CultureInfo.InvariantCulture;
        var cfg = r.Config;
        string P(double v) => (v * 100).ToString("0.0", ci) + "%";
        var sb = new StringBuilder();
        sb.AppendLine($"## 模擬結果：{(string.IsNullOrWhiteSpace(cfg.Name) ? "（未命名）" : cfg.Name)}");
        sb.AppendLine();
        sb.AppendLine($"- {cfg.Players} 人局，{a.GamesCompleted:N0} 局（{r.Status}，預定 {r.GamesRequested:N0}），主種子 {cfg.Seed}，座位順序 {cfg.SeatOrder}");
        var seconds = r.FinishedUtc is { } f ? (f - r.StartedUtc).TotalSeconds : (double?)null;
        sb.AppendLine($"- 耗時：{Duration(seconds)}" + (seconds is > 0 && a.GamesCompleted > 0 ? $"，{(a.GamesCompleted / seconds.Value).ToString("0.00", ci)} 局/秒" : ""));
        // files written before resolvedSeats existed (engine < 0.3.0) get the current build's commit as the property default, which would be wrong
        string commit = r.ResolvedSeats != null ? Short(r.EngineCommit) : "—";
        sb.AppendLine($"- 引擎 {r.EngineVersion}（commit {commit}），規則 {r.RulesVersion}-v{r.RulesRevision}");
        var revisions = (r.ResolvedSeats ?? new()).SelectMany(s => s.Revisions).GroupBy(kv => kv.Key).Select(g => $"{g.Key}-v{g.First().Value}").OrderBy(x => x, StringComparer.Ordinal).ToList();
        sb.AppendLine("- 策略版本：" + (revisions.Count > 0 ? string.Join("、", revisions) : "—"));
        sb.AppendLine();
        sb.AppendLine("| 座位 | 策略 | 設定 | 勝率 | ±95% | 平均分 | 標準差 |");
        sb.AppendLine("|---|---|---|---|---|---|---|");
        foreach (var s in a.Strategies)
        {
            var seat = cfg.Seats.FirstOrDefault(x => x.Id == s.SeatId);
            sb.AppendLine($"| {s.SeatId} | {s.Strategy} | {SeatParams(seat)} | {P(s.WinShare)} | ±{P(s.WinShareCi95)} | {s.AvgScore.ToString("0.0", ci)} | {s.StdScore.ToString("0.0", ci)} |");
        }
        if (r.TableSeats.Count > 0)
            sb.AppendLine().AppendLine("座位優勢（座位 1 = 起始總督）：" + string.Join("、", r.TableSeats.OrderBy(t => t.Seat).Select(t => $"座位 {t.Seat + 1} {P(t.WinShare)}")));
        if (a.HasGameRecords)
            sb.AppendLine($"平均回合數 {a.AvgRounds.ToString("0.0", ci)}，平均決策數 {a.AvgDecisions.ToString("0", ci)}／局");
        return sb.ToString().TrimEnd();
    }

    /// <summary>The parameters the config sets for the seat (valueModel shortened to its file name); "—" when it uses the defaults.</summary>
    private static string SeatParams(SeatConfig? seat)
    {
        if (seat == null || seat.Params.Count == 0) return "—";
        return string.Join("，", seat.Params.Select(kv =>
        {
            string v = kv.Value.ValueKind == JsonValueKind.String ? kv.Value.GetString() ?? "" : kv.Value.GetRawText();
            if (kv.Key == "valueModel") v = v.Replace('\\', '/').Split('/').Last();
            return $"{kv.Key} {v}";
        }));
    }

    private static string Short(string? commit) => string.IsNullOrEmpty(commit) ? "—" : commit.Length > 7 ? commit[..7] : commit;

    private static string Duration(double? seconds)
    {
        if (seconds == null) return "—";
        int s = (int)Math.Round(seconds.Value);
        return s >= 3600 ? $"{s / 3600} 小時 {s % 3600 / 60} 分" : s >= 60 ? $"{s / 60} 分 {s % 60} 秒" : $"{s} 秒";
    }
}
