using System.Text.Json;
using PuertoRico.Engine.Game;

namespace PuertoRico.Engine.Strategies.Mcts;

/// <summary>
/// Monte-Carlo tree search (UCT, "open loop"): every simulation clones the real state, re-seeds its random
/// generator (so chance events such as plantation draws differ per simulation) and walks the tree by applying
/// actions. Nodes are keyed by the action path only, never by a stored state.
/// Each simulation: select by UCT using the reward of the seat acting at that node, expand one untried action,
/// finish the game with the rollout policy (every seat plays <c>rolloutStrategy</c>), back up the final result
/// for every seat. Only the simulation count limits the work, never time, so results are reproducible.
/// Parameters: <c>simulations</c> (default 200 per decision), <c>exploration</c> (UCT constant, default 0.7, rewards are in [0,1]),
/// <c>rolloutStrategy</c> (any registered strategy name except mcts, default <c>random</c>: with 300 simulations random rollouts won 90% against three hand-written strategies, build-first rollouts only 57%, see docs/strategy-analysis.md), <c>rolloutMaxDecisions</c> (default 3000), <c>rolloutRounds</c> (default 8; 0 = play to the end; N = stop N rounds after the leaf and
/// rank the players by their current points: as strong as full rollouts at about half the cost, see docs/strategy-analysis.md).
/// <c>valueModel</c> (default empty = rollouts as above): path of a learned value function (LightGBM text model or MLP JSON, see
/// <see cref="IValueModel"/> and ml/README.md). With a model the leaf is not rolled out to the end: after <c>leafRollout</c> decisions
/// of the rollout policy (default 0) the model estimates every seat's reward; <c>rolloutRounds</c> is then ignored.
/// Selection, expansion and back-up are unchanged. Terminal leaves always use the real score.
/// The tree search sees the full state (opponents' VP chips included) as the architecture notes allow for MCTS.
/// </summary>
public sealed class MctsStrategy : IStrategy, IDecisionExplainer
{
    private const double WinWeight = 0.6;
    private static readonly IReadOnlyDictionary<string, JsonElement> NoParams = new Dictionary<string, JsonElement>();

    private readonly int _simulations;
    private readonly double _exploration;
    private readonly string _rolloutName;
    private readonly int _rolloutMaxDecisions;
    private readonly int _rolloutRounds;
    private readonly IValueModel? _value;
    private readonly int _leafRollout;
    private readonly string _valueName = "";
    private float[][]? _featRows;
    private float[]? _featScratch;
    private ulong _rng;
    private IStrategy[]? _rollout;
    private readonly List<GameAction> _legal = new(32);

    private sealed class Node
    {
        public readonly List<GameAction> Actions = new(4);
        public readonly List<Node> Kids = new(4);
        public int Visits;
        public int Actor = -1; // seat acting at this node (set once children exist)
        public readonly double[] Reward = new double[GameConstants.MaxPlayers];
        /// <summary>Win share per seat (1 for a sole winner, split on ties): display only, never used by the search.</summary>
        public readonly double[] Wins = new double[GameConstants.MaxPlayers];
        /// <summary>Sum of squared rewards per seat: display only (standard error of the mean).</summary>
        public readonly double[] RewardSq = new double[GameConstants.MaxPlayers];
    }

    public MctsStrategy(IReadOnlyDictionary<string, JsonElement> parameters, ulong seed)
    {
        _simulations = Math.Max(1, (int)StrategyRegistry.GetDouble(parameters, "simulations", 200));
        _exploration = StrategyRegistry.GetDouble(parameters, "exploration", 0.7);
        _rolloutName = StrategyRegistry.GetString(parameters, "rolloutStrategy", "random");
        _rolloutMaxDecisions = Math.Max(1, (int)StrategyRegistry.GetDouble(parameters, "rolloutMaxDecisions", 3000));
        _rolloutRounds = Math.Max(0, (int)StrategyRegistry.GetDouble(parameters, "rolloutRounds", 8));
        if (!StrategyRegistry.IsKnown(_rolloutName) || _rolloutName.Equals("mcts", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException($"Unknown or recursive rolloutStrategy '{_rolloutName}'.");
        string model = StrategyRegistry.GetString(parameters, "valueModel", "");
        _value = model.Length > 0 ? ValueModels.Load(model) : null;
        if (_value != null) _valueName = Path.GetFileName(model);
        _leafRollout = Math.Max(0, (int)StrategyRegistry.GetDouble(parameters, "leafRollout", 0));
        _rng = seed;
    }

    public SearchSummary? LastSearch { get; private set; }

    public GameAction ChooseAction(GameState state, IReadOnlyList<GameAction> legalActions)
    {
        LastSearch = null;
        if (legalActions.Count == 1) return legalActions[0];
        _rollout ??= CreateRollout(state.PlayerCount);

        var root = new Node();
        for (int i = 0; i < _simulations; i++)
        {
            var s = state.Clone();
            s.ReseedRng(Rng.Next(ref _rng));
            Simulate(root, s);
        }

        // Most visited legal action; ties by mean reward of the acting seat.
        int me = state.Actor;
        GameAction best = legalActions[0];
        double bestVisits = -1, bestMean = -1;
        var entries = new List<SearchSummary.Entry>(legalActions.Count);
        foreach (var a in legalActions)
        {
            int k = root.Actions.IndexOf(a);
            double visits = k < 0 ? 0 : root.Kids[k].Visits;
            double mean = visits > 0 ? root.Kids[k].Reward[me] / visits : 0;
            double winRate = visits > 0 ? root.Kids[k].Wins[me] / visits : 0;
            double stdError = 0;
            if (visits > 1)
            {
                double variance = Math.Max(0, (root.Kids[k].RewardSq[me] - visits * mean * mean) / (visits - 1));
                stdError = Math.Sqrt(variance / visits);
            }
            entries.Add(new SearchSummary.Entry(a, (int)visits, mean, k < 0 ? null : PrincipalLine(root.Kids[k]), winRate, stdError));
            if (visits > bestVisits || (visits == bestVisits && mean > bestMean)) { best = a; bestVisits = visits; bestMean = mean; }
        }
        LastSearch = new SearchSummary(_simulations, entries, _exploration, _rolloutName, _rolloutRounds, _valueName, _leafRollout);
        return best;
    }

    private const int MaxLineSteps = 8;

    /// <summary>Most visited reply chain below a node (display only).</summary>
    private static List<SearchSummary.LineStep> PrincipalLine(Node node)
    {
        var line = new List<SearchSummary.LineStep>();
        while (line.Count < MaxLineSteps && node.Kids.Count > 0)
        {
            int best = 0;
            for (int i = 1; i < node.Kids.Count; i++) if (node.Kids[i].Visits > node.Kids[best].Visits) best = i;
            line.Add(new SearchSummary.LineStep(node.Actor, node.Actions[best], node.Kids[best].Visits));
            node = node.Kids[best];
        }
        return line;
    }

    private IStrategy[] CreateRollout(int players)
    {
        var list = new IStrategy[players];
        for (int seat = 0; seat < players; seat++)
            list[seat] = StrategyRegistry.Create(_rolloutName, NoParams, Rng.Next(ref _rng), seat);
        return list;
    }

    private void Simulate(Node root, GameState s)
    {
        var path = new List<Node>(64) { root };
        var node = root;
        while (!s.IsOver)
        {
            var legal = _legal;
            Rules.GetLegalActions(s, legal);
            int actor = s.Actor;
            node.Actor = actor;

            // untried actions at this node (the legal set can differ between simulations because of chance events)
            int untried = 0;
            foreach (var a in legal) if (node.Actions.IndexOf(a) < 0) untried++;
            if (untried > 0)
            {
                int pick = Rng.NextInt(ref _rng, untried);
                GameAction chosen = legal[0];
                foreach (var a in legal)
                    if (node.Actions.IndexOf(a) < 0 && pick-- == 0) { chosen = a; break; }
                var kid = new Node();
                node.Actions.Add(chosen);
                node.Kids.Add(kid);
                Rules.Apply(s, chosen);
                path.Add(kid);
                break;
            }

            // all legal actions have children: UCT from the point of view of the acting seat
            double logN = Math.Log(Math.Max(1, node.Visits));
            int bestIndex = -1;
            double bestUct = double.NegativeInfinity;
            GameAction bestAction = legal[0];
            foreach (var a in legal)
            {
                int k = node.Actions.IndexOf(a);
                var kid = node.Kids[k];
                double uct = kid.Reward[actor] / kid.Visits + _exploration * Math.Sqrt(logN / kid.Visits);
                if (uct > bestUct) { bestUct = uct; bestIndex = k; bestAction = a; }
            }
            Rules.Apply(s, bestAction);
            node = node.Kids[bestIndex];
            path.Add(node);
        }

        // rollout (with a value model: only leafRollout decisions, then the model values the leaf)
        var buf = new List<GameAction>(32);
        int decisions = 0;
        int stopRound = _value == null && _rolloutRounds > 0 ? s.Round + _rolloutRounds : int.MaxValue;
        int maxDecisions = _value != null ? _leafRollout : int.MaxValue;
        while (!s.IsOver && s.Round < stopRound && decisions < maxDecisions)
        {
            Rules.GetLegalActions(s, buf);
            var action = buf.Count == 1 ? buf[0] : _rollout![s.Actor].ChooseAction(s, buf);
            Rules.Apply(s, action);
            if (++decisions >= _rolloutMaxDecisions && !s.IsOver) Rules.ForceEnd(s, EndFlags.DecisionLimit);
        }

        int players = s.PlayerCount;
        Span<double> reward = stackalloc double[GameConstants.MaxPlayers];
        Span<double> wins = stackalloc double[GameConstants.MaxPlayers];
        if (_value != null && !s.IsOver) ValueLeaf(s, reward, wins);
        else ScoreLeaf(s, reward, wins);
        foreach (var n in path)
        {
            n.Visits++;
            for (int seat = 0; seat < players; seat++) { n.Reward[seat] += reward[seat]; n.Wins[seat] += wins[seat]; n.RewardSq[seat] += reward[seat] * reward[seat]; }
        }
    }

    /// <summary>Model estimate of every seat's reward. The display-only win share is estimated as reward too (no separate win model).</summary>
    private void ValueLeaf(GameState s, Span<double> reward, Span<double> wins)
    {
        if (_featRows == null)
        {
            _featRows = new float[GameConstants.MaxPlayers][];
            for (int i = 0; i < _featRows.Length; i++) _featRows[i] = new float[ValueFeatures.Count];
            _featScratch = new float[ValueFeatures.ScratchLength];
        }
        ValueFeatures.ExtractAll(s, _featRows, _featScratch!);
        for (int seat = 0; seat < s.PlayerCount; seat++)
        {
            double v = Math.Clamp(_value!.Predict(_featRows[seat]), 0, 1);
            reward[seat] = v;
            wins[seat] = v;
        }
    }

    private static void ScoreLeaf(GameState s, Span<double> reward, Span<double> wins)
    {
        var score = Scoring.Score(s);
        int players = s.PlayerCount;
        for (int seat = 0; seat < players; seat++)
        {
            double win = Array.IndexOf(score.Winners, seat) >= 0 ? 1.0 / score.Winners.Length : 0.0;
            double rankScore = (players - score.Players[seat].Rank) / (double)(players - 1);
            reward[seat] = WinWeight * win + (1 - WinWeight) * rankScore;
            wins[seat] = win;
        }
    }

    /// <summary>Reward of every seat at a finished game (the training label of the value model, see <see cref="ValueFeatures"/>).</summary>
    public static void TerminalReward(GameState s, Span<double> reward, Span<double> wins) => ScoreLeaf(s, reward, wins);
}
