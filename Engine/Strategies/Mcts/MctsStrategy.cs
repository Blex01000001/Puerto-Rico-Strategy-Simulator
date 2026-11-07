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
/// <c>rolloutStrategy</c> (any registered strategy name except mcts, default <c>random</c>: with 300 simulations random rollouts won 90% against three hand-written strategies, build-first rollouts only 57%, see docs/strategy-analysis.md), <c>rolloutMaxDecisions</c> (default 3000).
/// The tree search sees the full state (opponents' VP chips included) as the architecture notes allow for MCTS.
/// </summary>
public sealed class MctsStrategy : IStrategy
{
    private const double WinWeight = 0.6;
    private static readonly IReadOnlyDictionary<string, JsonElement> NoParams = new Dictionary<string, JsonElement>();

    private readonly int _simulations;
    private readonly double _exploration;
    private readonly string _rolloutName;
    private readonly int _rolloutMaxDecisions;
    private ulong _rng;
    private IStrategy[]? _rollout;
    private readonly List<GameAction> _legal = new(32);

    private sealed class Node
    {
        public readonly List<GameAction> Actions = new(4);
        public readonly List<Node> Kids = new(4);
        public int Visits;
        public readonly double[] Reward = new double[GameConstants.MaxPlayers];
    }

    public MctsStrategy(IReadOnlyDictionary<string, JsonElement> parameters, ulong seed)
    {
        _simulations = Math.Max(1, (int)StrategyRegistry.GetDouble(parameters, "simulations", 200));
        _exploration = StrategyRegistry.GetDouble(parameters, "exploration", 0.7);
        _rolloutName = StrategyRegistry.GetString(parameters, "rolloutStrategy", "random");
        _rolloutMaxDecisions = Math.Max(1, (int)StrategyRegistry.GetDouble(parameters, "rolloutMaxDecisions", 3000));
        if (!StrategyRegistry.IsKnown(_rolloutName) || _rolloutName.Equals("mcts", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException($"Unknown or recursive rolloutStrategy '{_rolloutName}'.");
        _rng = seed;
    }

    public GameAction ChooseAction(GameState state, IReadOnlyList<GameAction> legalActions)
    {
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
        foreach (var a in legalActions)
        {
            int k = root.Actions.IndexOf(a);
            double visits = k < 0 ? 0 : root.Kids[k].Visits;
            double mean = visits > 0 ? root.Kids[k].Reward[me] / visits : 0;
            if (visits > bestVisits || (visits == bestVisits && mean > bestMean)) { best = a; bestVisits = visits; bestMean = mean; }
        }
        return best;
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

        // rollout
        var buf = new List<GameAction>(32);
        int decisions = 0;
        while (!s.IsOver)
        {
            Rules.GetLegalActions(s, buf);
            var action = buf.Count == 1 ? buf[0] : _rollout![s.Actor].ChooseAction(s, buf);
            Rules.Apply(s, action);
            if (++decisions >= _rolloutMaxDecisions && !s.IsOver) Rules.ForceEnd(s, EndFlags.DecisionLimit);
        }

        var score = Scoring.Score(s);
        int players = s.PlayerCount;
        Span<double> reward = stackalloc double[GameConstants.MaxPlayers];
        for (int seat = 0; seat < players; seat++)
        {
            double win = Array.IndexOf(score.Winners, seat) >= 0 ? 1.0 / score.Winners.Length : 0.0;
            double rankScore = (players - score.Players[seat].Rank) / (double)(players - 1);
            reward[seat] = WinWeight * win + (1 - WinWeight) * rankScore;
        }
        foreach (var n in path)
        {
            n.Visits++;
            for (int seat = 0; seat < players; seat++) n.Reward[seat] += reward[seat];
        }
    }
}
