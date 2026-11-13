using System.Collections.Concurrent;
using PuertoRico.Engine.Events;
using PuertoRico.Engine.Game;
using PuertoRico.Engine.Simulation;

// Run: dotnet run -c Release --project tools/sparring -- mcts/sparring/4p-mcts-vs-3cheap.json [games]
// Plays the table of a config file and prints, per strategy, how it plays: roles chosen, tempo per round, shipping, selling,
// spoilage, buildings and plantations. Used to compare a hand-written strategy with an MCTS sparring partner at the same table
// (docs/strategy-analysis.md section 9). Seats with the same strategy name are pooled.
var cfg = SimulationConfig.Load(args[0]);
int games = args.Length > 1 ? int.Parse(args[1]) : cfg.Games;
int P = cfg.Players;
const int G = GameConstants.GoodCount, T = GameConstants.TileTypes, MaxRound = 16;
var stratOf = cfg.Seats.ToDictionary(s => s.Id, s => s.Strategy);

var all = new ConcurrentBag<(GameRecord Rec, Collect Sink, GameState Final)>();
Parallel.For(0, games, i =>
{
    var sink = new Collect(P);
    var rec = GameRunner.Play(cfg, i, sink, out var final);
    all.Add((rec, sink, final));
});

var stats = new SortedDictionary<string, Stat>();
double roundsSum = 0;
foreach (var (rec, sink, final) in all)
{
    roundsSum += rec.Rounds;
    foreach (var p in rec.Players)
    {
        string name = stratOf[p.SeatId];
        if (!stats.TryGetValue(name, out var st)) stats[name] = st = new Stat();
        int seat = p.Seat;
        st.N++;
        st.Wins += rec.Winners.Contains(seat) ? 1.0 / rec.Winners.Count : 0;
        st.Vp += p.Vp; st.Chips += p.Chips; st.BuildVp += p.BuildingPoints; st.Bonus += p.BonusPoints; st.CoinsEnd += p.Coins;
        for (int k = 0; k < p.Buildings!.Count; k++) { st.Built[p.Buildings[k]]++; st.BuiltRound[p.Buildings[k]] += p.BuiltRounds![k]; }
        for (int t = 0; t < T; t++) st.Tiles[t] += p.Tiles![t];
        var ps = sink.Seats[seat];
        for (int r = 0; r < 7; r++) for (int b = 0; b < 3; b++) st.Roles[r, b] += ps.Roles[r, b];
        for (int g = 0; g < G; g++)
        {
            st.Produced[g] += ps.Produced[g]; st.Shipped[g] += ps.Shipped[g]; st.Sold[g] += ps.Sold[g];
            int left = final.Goods[seat * G + g];
            st.Left[g] += left;
            st.Spoiled[g] += ps.Produced[g] - ps.Shipped[g] - ps.Sold[g] - left;
        }
        st.Loads += ps.Loads; st.WharfLoads += ps.WharfLoads; st.SaleCoins += ps.SaleCoins; st.RoleCoins += ps.RoleCoins;
        st.CaptainPhases += sink.CaptainPhases; st.CaptainShut += ps.CaptainShut; st.CaptainWithGoods += ps.CaptainWithGoods;
        st.TraderPhases += sink.TraderPhases; st.TraderWithGoods += ps.TraderWithGoods;
        for (int r = 1; r <= MaxRound; r++)
        {
            if (sink.Seen[r] == 0) continue;
            st.RoundN[r]++;
            for (int k = 0; k < Collect.K; k++) st.Traj[r, k] += ps.Traj[r, k];
        }
    }
}

int n = all.Count;
Console.WriteLine($"## {cfg.Name}: {n} games, {P} players, seatOrder {cfg.SeatOrder}, avg rounds {roundsSum / n:0.0}");
Console.WriteLine();
string Head(string first) => $"| {first} | " + string.Join(" | ", stats.Keys) + " |\n|---|" + string.Concat(stats.Keys.Select(_ => "---|"));
void Row(string label, Func<Stat, string> f) => Console.WriteLine($"| {label} | " + string.Join(" | ", stats.Values.Select(f)) + " |");
string Avg(double sum, Stat s, string fmt = "0.0") => (sum / s.N).ToString(fmt);

Console.WriteLine(Head("per game (per seat)"));
Row("seats", s => $"{s.N / n}");
Row("win rate", s => $"{100 * s.Wins / s.N:0.0}%");
Row("VP (chips / buildings / bonus)", s => $"{Avg(s.Vp, s)} ({Avg(s.Chips, s)} / {Avg(s.BuildVp, s)} / {Avg(s.Bonus, s)})");
Row("plantations + quarries", s => Avg(s.Tiles.Sum(), s));
Row("  corn / indigo / sugar / tobacco / coffee / quarry", s => string.Join(" / ", s.Tiles.Select(t => Avg(t, s))));
Row("buildings", s => Avg(s.Built.Sum(), s));
Row("barrels produced", s => Avg(s.Produced.Sum(), s));
Row("  corn / indigo / sugar / tobacco / coffee", s => string.Join(" / ", s.Produced.Select(t => Avg(t, s))));
Row("barrels shipped", s => Avg(s.Shipped.Sum(), s));
Row("  loads (public + wharf)", s => $"{Avg(s.Loads, s)} + {Avg(s.WharfLoads, s, "0.00")}");
Row("  barrels per load", s => $"{s.Shipped.Sum() / Math.Max(1, s.Loads + s.WharfLoads):0.00}");
Row("barrels sold", s => Avg(s.Sold.Sum(), s, "0.00"));
Row("  corn / indigo / sugar / tobacco / coffee", s => string.Join(" / ", s.Sold.Select(t => Avg(t, s, "0.00"))));
Row("coins from sales", s => Avg(s.SaleCoins, s));
Row("coins picked up on role cards", s => Avg(s.RoleCoins, s));
Row("barrels spoiled", s => Avg(s.Spoiled.Sum(), s));
Row("  corn / indigo / sugar / tobacco / coffee", s => string.Join(" / ", s.Spoiled.Select(t => Avg(t, s, "0.00"))));
Row("barrels left at game end", s => Avg(s.Left.Sum(), s));
Row("coins left at game end", s => Avg(s.CoinsEnd, s));
Row("captain phases: had goods, shipped nothing", s => $"{100 * s.CaptainShut / Math.Max(1, s.CaptainWithGoods):0}% of {Avg(s.CaptainWithGoods, s)}");
Row("trader phases: had goods at start", s => $"{Avg(s.TraderWithGoods, s)} of {Avg(s.TraderPhases, s)}");
Console.WriteLine();

Console.WriteLine("Roles chosen per game (rounds 1-4 / 5-8 / 9+):");
Console.WriteLine(Head("role"));
for (int r = 0; r < GameConstants.RoleCount(P); r++)
    Row(((Role)r).ToString(), s => $"{(s.Roles[r, 0] + s.Roles[r, 1] + s.Roles[r, 2]) / s.N:0.00} ({s.Roles[r, 0] / s.N:0.00} / {s.Roles[r, 1] / s.N:0.00} / {s.Roles[r, 2] / s.N:0.00})");
Console.WriteLine();

Console.WriteLine("Buildings: % of games bought @ average round");
Console.WriteLine(Head("building"));
for (int b = 0; b < GameConstants.BuildingCount; b++)
{
    if (stats.Values.All(s => s.Built[b] < 0.03 * s.N)) continue;
    Row(Buildings.All[b].Name, s => s.Built[b] == 0 ? "-" : $"{100 * s.Built[b] / s.N:0}% @ {s.BuiltRound[b] / s.Built[b]:0.0}");
}
Console.WriteLine();

string[] cols = { "coins", "VP chips", "buildings", "building VP", "tiles", "colonists", "barrels held", "barrels shipped so far", "coins earned so far", "coins spent on buildings so far" };
for (int k = 0; k < Collect.K; k++)
{
    Console.WriteLine($"Start of round: {cols[k]}");
    Console.WriteLine(Head("round"));
    for (int r = 2; r <= MaxRound; r++)
    {
        if (stats.Values.First().RoundN[r] < 0.5 * stats.Values.First().N) break;
        Row(r.ToString(), s => $"{s.Traj[r, k] / s.RoundN[r]:0.0}");
    }
    Console.WriteLine();
}

sealed class SeatStat
{
    public double[,] Roles = new double[7, 3];
    public double[] Produced = new double[GameConstants.GoodCount], Shipped = new double[GameConstants.GoodCount], Sold = new double[GameConstants.GoodCount];
    public double Loads, WharfLoads, SaleCoins, RoleCoins, CaptainShut, CaptainWithGoods, TraderWithGoods, Earned, SpentBuild;
    public double[,] Traj = new double[17, Collect.K];
    public bool HadGoods, ShippedThisPhase;
}

/// <summary>Follows one game through the "state before each decision" callbacks and derives what happened in between from state differences.</summary>
sealed class Collect : IGameEventSink
{
    public const int K = 10;
    private const int G = GameConstants.GoodCount, T = GameConstants.TileTypes, B = GameConstants.BuildingCount;
    public readonly SeatStat[] Seats;
    public readonly int[] Seen = new int[17];
    public int CaptainPhases, TraderPhases;
    private readonly int _p;
    private int[]? _goods, _coins;
    private Phase _lastPhase = Phase.ChooseRole;
    private int _lastRound;

    public Collect(int players) { _p = players; Seats = Enumerable.Range(0, players).Select(_ => new SeatStat()).ToArray(); }
    public bool Enabled => true;

    public void OnDecision(GameState s, GameAction a)
    {
        // production = any increase of a seat's barrels since the previous decision (only the Craftsman adds barrels)
        if (_goods != null)
            for (int p = 0; p < _p; p++)
            {
                for (int g = 0; g < G; g++)
                {
                    int d = s.Goods[p * G + g] - _goods[p * G + g];
                    if (d > 0) Seats[p].Produced[g] += d;
                }
                int dc = s.Coins[p] - _coins![p];
                if (dc > 0) Seats[p].Earned += dc; else Seats[p].SpentBuild -= dc;
            }
        _goods = (int[])s.Goods.Clone(); _coins = (int[])s.Coins.Clone();

        if (s.Round != _lastRound && s.Round <= 16)
        {
            _lastRound = s.Round; Seen[s.Round] = 1;
            for (int p = 0; p < _p; p++)
            {
                var t = Seats[p].Traj; int r = s.Round;
                int nb = 0, bvp = 0;
                for (int b = 0; b < B; b++) if (s.BuildingOwned[p * B + b] != 0) { nb++; bvp += Buildings.All[b].Vp; }
                t[r, 0] = s.Coins[p]; t[r, 1] = s.VpChips[p]; t[r, 2] = nb; t[r, 3] = bvp; t[r, 4] = s.TileCount(p);
                t[r, 5] = s.ColonistsOnBoard(p) + s.SanJuan[p]; t[r, 6] = s.GoodTotal(p); t[r, 7] = Seats[p].Shipped.Sum();
                t[r, 8] = Seats[p].Earned; t[r, 9] = Seats[p].SpentBuild;
            }
        }

        // phase bookkeeping: entering / leaving the Captain's loading step, entering the Trader
        if (s.Phase != _lastPhase)
        {
            if (_lastPhase == Phase.Captain) CloseCaptain();
            if (s.Phase == Phase.Captain)
            {
                CaptainPhases++;
                for (int p = 0; p < _p; p++) { Seats[p].HadGoods = s.GoodTotal(p) > 0; Seats[p].ShippedThisPhase = false; }
            }
            if (s.Phase == Phase.Trader)
            {
                TraderPhases++;
                for (int p = 0; p < _p; p++) if (s.GoodTotal(p) > 0) Seats[p].TraderWithGoods++;
            }
            _lastPhase = s.Phase;
        }

        var me = Seats[s.Actor];
        int bucket = s.Round <= 4 ? 0 : s.Round <= 8 ? 1 : 2;
        switch (a.Type)
        {
            case ActionType.ChooseRole:
                me.Roles[a.A, bucket]++;
                me.RoleCoins += s.RoleCoins[a.A];
                break;
            case ActionType.LoadShip:
                me.Shipped[a.A] += Math.Min(s.Goods[s.Actor * G + a.A], s.ShipCap[a.B] - s.ShipLoad[a.B]);
                me.Loads++; me.ShippedThisPhase = true;
                break;
            case ActionType.LoadWharf:
                me.Shipped[a.A] += s.Goods[s.Actor * G + a.A];
                me.WharfLoads++; me.ShippedThisPhase = true;
                break;
            case ActionType.Sell:
                me.Sold[a.A]++;
                me.SaleCoins += Rules.SalePrice(s, s.Actor, a.A);
                break;
        }
    }

    private void CloseCaptain()
    {
        foreach (var st in Seats)
            if (st.HadGoods) { st.CaptainWithGoods++; if (!st.ShippedThisPhase) st.CaptainShut++; }
    }
}

sealed class Stat
{
    private const int G = GameConstants.GoodCount;
    public double N, Wins, Vp, Chips, BuildVp, Bonus, CoinsEnd, Loads, WharfLoads, SaleCoins, RoleCoins;
    public double CaptainPhases, CaptainShut, CaptainWithGoods, TraderPhases, TraderWithGoods;
    public double[] Built = new double[GameConstants.BuildingCount], BuiltRound = new double[GameConstants.BuildingCount];
    public double[] Tiles = new double[GameConstants.TileTypes];
    public double[] Produced = new double[G], Shipped = new double[G], Sold = new double[G], Left = new double[G], Spoiled = new double[G];
    public double[,] Roles = new double[7, 3];
    public double[] RoundN = new double[17];
    public double[,] Traj = new double[17, Collect.K];
}
