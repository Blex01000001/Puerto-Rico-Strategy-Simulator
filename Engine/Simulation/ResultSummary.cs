using System.Globalization;
using System.Text;
using System.Text.Json;

namespace PuertoRico.Engine.Simulation;

/// <summary>
/// A result file as short Markdown to paste into a chat with an AI (Dashboard「複製摘要給 AI」; the ML UI has the same kind of text for its match records):
/// what was played, how long it took, the win shares with their 95% intervals and the versions. No per-game data, no machine paths.
/// Chinese by default; <c>english: true</c> writes the same text in English (the Dashboard passes its language).
/// </summary>
public static class ResultSummary
{
    public static string ToMarkdown(SimulationResult r, ResultAnalysis a, bool english = false)
    {
        string T(string zh, string en) => english ? en : zh;
        string sep = english ? ", " : "、";
        var ci = CultureInfo.InvariantCulture;
        var cfg = r.Config;
        string P(double v) => (v * 100).ToString("0.0", ci) + "%";
        var sb = new StringBuilder();
        sb.AppendLine(T("## 模擬結果：", "## Simulation result: ") + (string.IsNullOrWhiteSpace(cfg.Name) ? T("（未命名）", "(unnamed)") : cfg.Name));
        sb.AppendLine();
        sb.AppendLine(english
            ? $"- {cfg.Players} players, {a.GamesCompleted:N0} games ({r.Status}, {r.GamesRequested:N0} planned), main seed {cfg.Seed}, seat order {cfg.SeatOrder}"
            : $"- {cfg.Players} 人局，{a.GamesCompleted:N0} 局（{r.Status}，預定 {r.GamesRequested:N0}），主種子 {cfg.Seed}，座位順序 {cfg.SeatOrder}");
        var seconds = r.FinishedUtc is { } f ? (f - r.StartedUtc).TotalSeconds : (double?)null;
        sb.AppendLine(T("- 耗時：", "- Duration: ") + Duration(seconds, english) + (seconds is > 0 && a.GamesCompleted > 0 ? T("，", ", ") + (a.GamesCompleted / seconds.Value).ToString("0.00", ci) + T(" 局/秒", " games/s") : ""));
        // files written before resolvedSeats existed (engine < 0.3.0) get the current build's commit as the property default, which would be wrong
        string commit = r.ResolvedSeats != null ? Short(r.EngineCommit) : "—";
        sb.AppendLine(english
            ? $"- Engine {r.EngineVersion} (commit {commit}), rules {r.RulesVersion}-v{r.RulesRevision}"
            : $"- 引擎 {r.EngineVersion}（commit {commit}），規則 {r.RulesVersion}-v{r.RulesRevision}");
        var revisions = (r.ResolvedSeats ?? new()).SelectMany(s => s.Revisions).GroupBy(kv => kv.Key).Select(g => $"{g.Key}-v{g.First().Value}").OrderBy(x => x, StringComparer.Ordinal).ToList();
        sb.AppendLine(T("- 策略版本：", "- Strategy versions: ") + (revisions.Count > 0 ? string.Join(sep, revisions) : "—"));
        sb.AppendLine();
        sb.AppendLine(T("| 座位 | 策略 | 設定 | 勝率 | ±95% | 平均分 | 標準差 |", "| Seat | Strategy | Settings | Win rate | ±95% | Average score | Std dev |"));
        sb.AppendLine("|---|---|---|---|---|---|---|");
        foreach (var s in a.Strategies)
        {
            var seat = cfg.Seats.FirstOrDefault(x => x.Id == s.SeatId);
            sb.AppendLine($"| {s.SeatId} | {s.Strategy} | {SeatParams(seat, english)} | {P(s.WinShare)} | ±{P(s.WinShareCi95)} | {s.AvgScore.ToString("0.0", ci)} | {s.StdScore.ToString("0.0", ci)} |");
        }
        if (r.TableSeats.Count > 0)
            sb.AppendLine().AppendLine(T("座位優勢（座位 1 = 起始總督）：", "Seat advantage (seat 1 = starting governor): ") + string.Join(sep, r.TableSeats.OrderBy(t => t.Seat).Select(t => T($"座位 {t.Seat + 1} {P(t.WinShare)}", $"seat {t.Seat + 1} {P(t.WinShare)}"))));
        if (a.HasGameRecords)
            sb.AppendLine(english
                ? $"Average rounds {a.AvgRounds.ToString("0.0", ci)}, average decisions {a.AvgDecisions.ToString("0", ci)} / game"
                : $"平均回合數 {a.AvgRounds.ToString("0.0", ci)}，平均決策數 {a.AvgDecisions.ToString("0", ci)}／局");
        return sb.ToString().TrimEnd();
    }

    /// <summary>The parameters the config sets for the seat (valueModel shortened to its file name); "—" when it uses the defaults.</summary>
    private static string SeatParams(SeatConfig? seat, bool english)
    {
        if (seat == null || seat.Params.Count == 0) return "—";
        return string.Join(english ? ", " : "，", seat.Params.Select(kv =>
        {
            string v = kv.Value.ValueKind == JsonValueKind.String ? kv.Value.GetString() ?? "" : kv.Value.GetRawText();
            if (kv.Key == "valueModel") v = v.Replace('\\', '/').Split('/').Last();
            return $"{kv.Key} {v}";
        }));
    }

    private static string Short(string? commit) => string.IsNullOrEmpty(commit) ? "—" : commit.Length > 7 ? commit[..7] : commit;

    private static string Duration(double? seconds, bool english)
    {
        if (seconds == null) return "—";
        int s = (int)Math.Round(seconds.Value);
        return english
            ? (s >= 3600 ? $"{s / 3600} h {s % 3600 / 60} min" : s >= 60 ? $"{s / 60} min {s % 60} s" : $"{s} s")
            : (s >= 3600 ? $"{s / 3600} 小時 {s % 3600 / 60} 分" : s >= 60 ? $"{s / 60} 分 {s % 60} 秒" : $"{s} 秒");
    }
}
