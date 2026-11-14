using System.Collections.Concurrent;
using System.Globalization;
using System.Text.Json;

namespace PuertoRico.Engine.Strategies.Mcts;

/// <summary>
/// Learned position value: features (<see cref="ValueFeatures"/>, from one seat's point of view) -> expected MCTS reward
/// of that seat (0.6 × win + 0.4 × rank score, in [0,1]). Models are trained offline (ml/) and only evaluated here,
/// in plain C# (no ML library), so inference is deterministic and has no native dependency. Instances are immutable
/// and shared between threads.
/// </summary>
public interface IValueModel
{
    double Predict(ReadOnlySpan<float> features);
}

public static class ValueModels
{
    // Immutable, read-only models keyed by full path: safe to share (no randomness, no mutable state).
    private static readonly ConcurrentDictionary<string, IValueModel> Cache = new();

    /// <summary>Loads (once per path) a LightGBM text model (*.txt) or an MLP exported as JSON (*.json).</summary>
    public static IValueModel Load(string path)
    {
        string full = Path.GetFullPath(path);
        return Cache.GetOrAdd(full, p =>
        {
            if (!File.Exists(p)) throw new ArgumentException($"valueModel '{path}' does not exist");
            return p.EndsWith(".json", StringComparison.OrdinalIgnoreCase)
                ? MlpValueModel.Parse(File.ReadAllText(p))
                : LightGbmValueModel.Parse(File.ReadAllLines(p));
        });
    }

    internal static void CheckFeatureNames(IReadOnlyList<string> names, string what)
    {
        var expected = ValueFeatures.Names;
        if (names.Count != expected.Length)
            throw new InvalidDataException($"{what}: {names.Count} features, the engine has {expected.Length} (feature version {ValueFeatures.Version}); retrain the model");
        for (int i = 0; i < expected.Length; i++)
            if (names[i] != expected[i])
                throw new InvalidDataException($"{what}: feature {i} is '{names[i]}', the engine expects '{expected[i]}'; retrain the model");
    }

    internal static double Sigmoid(double x) => 1.0 / (1.0 + Math.Exp(-x));
}

/// <summary>
/// Evaluates a LightGBM model saved with <c>Booster.save_model</c> (text format, numerical splits only).
/// Output transform: sigmoid for <c>cross_entropy</c>/<c>binary</c> objectives, identity for regression.
/// </summary>
public sealed class LightGbmValueModel : IValueModel
{
    private sealed class Tree
    {
        public int[] Feature = Array.Empty<int>();
        public double[] Threshold = Array.Empty<double>();
        public int[] DecisionType = Array.Empty<int>();
        public int[] Left = Array.Empty<int>();
        public int[] Right = Array.Empty<int>();
        public double[] Leaf = Array.Empty<double>();
    }

    /// <summary>Flattened split node: child &gt;= 0 is a node index, child &lt; 0 is ~leaf index.</summary>
    private struct FlatNode
    {
        public int Feature;
        public double Threshold;
        public int Left, Right;
    }

    private readonly Tree[] _trees;
    private readonly bool _sigmoid;
    private readonly double _sigmoidScale;
    private readonly bool _average;
    // fast path, used when no split has a missing-value rule (the usual case: features never contain NaN)
    private readonly bool _plain;
    private readonly FlatNode[] _nodes;
    private readonly int[] _roots; // node index, or ~leaf for single-leaf trees
    private readonly double[] _leaves;

    private LightGbmValueModel(Tree[] trees, bool sigmoid, double scale, bool average)
    {
        _trees = trees; _sigmoid = sigmoid; _sigmoidScale = scale; _average = average;
        _plain = trees.All(t => t.DecisionType.All(d => ((d >> 2) & 3) == 0 && (d & 1) == 0));
        var nodes = new List<FlatNode>();
        var leaves = new List<double>();
        _roots = new int[trees.Length];
        for (int k = 0; k < trees.Length; k++)
        {
            var t = trees[k];
            int nodeBase = nodes.Count, leafBase = leaves.Count;
            leaves.AddRange(t.Leaf);
            if (t.Feature.Length == 0) { _roots[k] = ~leafBase; continue; }
            _roots[k] = nodeBase;
            int Map(int c) => c >= 0 ? nodeBase + c : ~(leafBase + ~c);
            for (int i = 0; i < t.Feature.Length; i++)
                nodes.Add(new FlatNode { Feature = t.Feature[i], Threshold = t.Threshold[i], Left = Map(t.Left[i]), Right = Map(t.Right[i]) });
        }
        _nodes = nodes.ToArray();
        _leaves = leaves.ToArray();
    }

    public int TreeCount => _trees.Length;

    public static LightGbmValueModel Parse(IReadOnlyList<string> lines)
    {
        string objective = "regression";
        bool average = false;
        string[]? names = null;
        var trees = new List<Tree>();
        Tree? cur = null;
        foreach (var raw in lines)
        {
            string line = raw.Trim();
            if (line == "end of trees") break;
            if (line.StartsWith("Tree=", StringComparison.Ordinal)) { cur = new Tree(); trees.Add(cur); continue; }
            if (line == "average_output") { average = true; continue; }
            int eq = line.IndexOf('=');
            if (eq <= 0) continue;
            string key = line[..eq], val = line[(eq + 1)..];
            if (cur == null)
            {
                if (key == "objective") objective = val;
                else if (key == "feature_names") names = val.Split(' ', StringSplitOptions.RemoveEmptyEntries);
                else if (key == "num_class" && val != "1") throw new InvalidDataException("LightGBM model: only single-output models are supported");
                continue;
            }
            switch (key)
            {
                case "split_feature": cur.Feature = Ints(val); break;
                case "threshold": cur.Threshold = Doubles(val); break;
                case "decision_type": cur.DecisionType = Ints(val); break;
                case "left_child": cur.Left = Ints(val); break;
                case "right_child": cur.Right = Ints(val); break;
                case "leaf_value": cur.Leaf = Doubles(val); break;
                case "num_cat" when val != "0": throw new InvalidDataException("LightGBM model: categorical splits are not supported");
            }
        }
        if (names == null) throw new InvalidDataException("LightGBM model: no feature_names line");
        ValueModels.CheckFeatureNames(names, "LightGBM model");
        if (trees.Count == 0) throw new InvalidDataException("LightGBM model: no trees");

        string obj = objective.Split(' ')[0];
        bool sigmoid = obj is "cross_entropy" or "xentropy" or "binary";
        double scale = 1;
        foreach (var part in objective.Split(' '))
            if (part.StartsWith("sigmoid:", StringComparison.Ordinal)) scale = double.Parse(part[8..], CultureInfo.InvariantCulture);
        if (!sigmoid && !obj.StartsWith("regression", StringComparison.Ordinal))
            throw new InvalidDataException($"LightGBM model: unsupported objective '{objective}'");
        return new LightGbmValueModel(trees.ToArray(), sigmoid, obj == "binary" ? scale : 1, average);
    }

    private static int[] Ints(string v) => v.Split(' ', StringSplitOptions.RemoveEmptyEntries).Select(x => int.Parse(x, CultureInfo.InvariantCulture)).ToArray();
    private static double[] Doubles(string v) => v.Split(' ', StringSplitOptions.RemoveEmptyEntries).Select(x => double.Parse(x, CultureInfo.InvariantCulture)).ToArray();

    public double Raw(ReadOnlySpan<float> x)
    {
        if (_plain)
        {
            double total = 0;
            var nodes = _nodes;
            foreach (int root in _roots)
            {
                int node = root;
                while (node >= 0)
                {
                    ref readonly var n = ref nodes[node];
                    node = x[n.Feature] <= n.Threshold ? n.Left : n.Right;
                }
                total += _leaves[~node];
            }
            return _average ? total / _roots.Length : total;
        }
        double sum = 0;
        foreach (var t in _trees)
        {
            if (t.Feature.Length == 0) { sum += t.Leaf[0]; continue; }
            int node = 0;
            while (node >= 0)
            {
                double v = x[t.Feature[node]];
                int dt = t.DecisionType[node];
                bool defaultLeft = (dt & 2) != 0;
                int missing = (dt >> 2) & 3; // 0 none, 1 zero, 2 NaN
                bool left;
                if (double.IsNaN(v) && missing != 2) v = 0;
                if ((missing == 1 && Math.Abs(v) <= 1e-35) || (missing == 2 && double.IsNaN(v))) left = defaultLeft;
                else left = v <= t.Threshold[node];
                node = left ? t.Left[node] : t.Right[node];
            }
            sum += t.Leaf[~node];
        }
        return _average ? sum / _trees.Length : sum;
    }

    public double Predict(ReadOnlySpan<float> x)
    {
        double raw = Raw(x);
        return _sigmoid ? ValueModels.Sigmoid(_sigmoidScale * raw) : Math.Clamp(raw, 0, 1);
    }
}

/// <summary>
/// Fully connected network exported as JSON by ml/train_mlp.py:
/// <c>{ "format": "mlp", "features": [...], "mean": [...], "scale": [...], "layers": [{ "weights": [[...] per output], "bias": [...] }], "activation": "relu", "output": "sigmoid" }</c>.
/// Input is standardised as (x - mean) / scale; hidden layers use the activation, the last layer the output transform.
/// </summary>
public sealed class MlpValueModel : IValueModel
{
    // First layer with the standardisation folded in: h = b0' + sum_i x_i * W0t[i], where W0t[i] = W0[:, i] / scale_i and
    // b0' = b0 - sum_i W0[:, i] * mean_i / scale_i. The raw features are mostly zero, so zero inputs are skipped.
    private readonly float[] _w0t; // [in * hidden0]
    private readonly float[] _b0;
    private readonly int _in0, _h0;
    private readonly float[][] _w; // later layers, transposed [in * out]
    private readonly float[][] _b;
    private readonly int[] _in, _out;
    private readonly bool _sigmoidOut;
    private readonly int _width;

    private MlpValueModel(float[] w0t, float[] b0, int in0, float[][] w, float[][] b, int[] inSize, int[] outSize, bool sigmoidOut)
    {
        _w0t = w0t; _b0 = b0; _in0 = in0; _h0 = b0.Length;
        _w = w; _b = b; _in = inSize; _out = outSize; _sigmoidOut = sigmoidOut;
        _width = Math.Max(_h0, outSize.Length > 0 ? outSize.Max() : 1);
    }

    public static MlpValueModel Parse(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        if (root.GetProperty("format").GetString() != "mlp") throw new InvalidDataException("MLP model: format must be 'mlp'");
        var names = root.GetProperty("features").EnumerateArray().Select(e => e.GetString() ?? "").ToList();
        ValueModels.CheckFeatureNames(names, "MLP model");
        string act = root.TryGetProperty("activation", out var a) ? a.GetString() ?? "relu" : "relu";
        if (act != "relu") throw new InvalidDataException($"MLP model: unsupported activation '{act}'");
        string output = root.TryGetProperty("output", out var o) ? o.GetString() ?? "sigmoid" : "sigmoid";
        float[] F(JsonElement e) => e.EnumerateArray().Select(v => v.GetSingle()).ToArray();
        var mean = F(root.GetProperty("mean"));
        var scale = F(root.GetProperty("scale"));
        if (mean.Length != names.Count || scale.Length != names.Count) throw new InvalidDataException("MLP model: mean/scale length");
        var layers = new List<(float[][] Rows, float[] Bias)>();
        int prev = names.Count;
        foreach (var layer in root.GetProperty("layers").EnumerateArray())
        {
            var rows = layer.GetProperty("weights").EnumerateArray().Select(F).ToArray();
            var bias = F(layer.GetProperty("bias"));
            if (rows.Length != bias.Length || rows.Any(r => r.Length != prev)) throw new InvalidDataException("MLP model: layer shape");
            layers.Add((rows, bias));
            prev = bias.Length;
        }
        if (layers.Count < 2 || prev != 1) throw new InvalidDataException("MLP model: needs at least one hidden layer and one output");

        int n0 = names.Count;
        var (r0, bias0) = layers[0];
        int h0 = bias0.Length;
        var w0t = new float[n0 * h0];
        var b0 = new float[h0];
        for (int j = 0; j < h0; j++)
        {
            double bj = bias0[j];
            for (int i = 0; i < n0; i++)
            {
                double inv = scale[i] > 0 ? 1.0 / scale[i] : 1.0;
                w0t[i * h0 + j] = (float)(r0[j][i] * inv);
                bj -= r0[j][i] * mean[i] * inv;
            }
            b0[j] = (float)bj;
        }
        var ws = layers.Skip(1).Select(l =>
        {
            int outN = l.Rows.Length, inN = l.Rows[0].Length;
            var t = new float[inN * outN];
            for (int j = 0; j < outN; j++) for (int i = 0; i < inN; i++) t[i * outN + j] = l.Rows[j][i];
            return t;
        }).ToArray();
        var bs = layers.Skip(1).Select(l => l.Bias).ToArray();
        var ins = layers.Skip(1).Select(l => l.Rows[0].Length).ToArray();
        var outs = layers.Skip(1).Select(l => l.Bias.Length).ToArray();
        return new MlpValueModel(w0t, b0, n0, ws, bs, ins, outs, output == "sigmoid");
    }

    /// <summary>
    /// Every output accumulates its inputs in index order (y += x_i * row_i, element-wise), so the result does not depend on the
    /// SIMD width of the machine: the same model gives bit-identical values everywhere (reproducibility).
    /// </summary>
    public double Predict(ReadOnlySpan<float> x)
    {
        Span<float> a = _width <= 1024 ? stackalloc float[_width] : new float[_width];
        Span<float> b = _width <= 1024 ? stackalloc float[_width] : new float[_width];
        var h = a[.._h0];
        _b0.CopyTo(h);
        for (int i = 0; i < _in0; i++)
            if (x[i] != 0) Axpy(x[i], new ReadOnlySpan<float>(_w0t, i * _h0, _h0), h);
        Relu(h);
        for (int l = 0; l < _w.Length; l++)
        {
            int n = _in[l], m = _out[l];
            var y = b[..m];
            _b[l].CopyTo(y);
            for (int i = 0; i < n; i++)
                if (a[i] != 0) Axpy(a[i], new ReadOnlySpan<float>(_w[l], i * m, m), y);
            if (l < _w.Length - 1) Relu(y);
            var t = a; a = b; b = t;
        }
        double result = a[0];
        return _sigmoidOut ? ValueModels.Sigmoid(result) : Math.Clamp(result, 0, 1);
    }

    private static void Axpy(float s, ReadOnlySpan<float> row, Span<float> y)
    {
        int vw = System.Numerics.Vector<float>.Count, j = 0;
        var vs = new System.Numerics.Vector<float>(s);
        for (; j <= y.Length - vw; j += vw)
            (new System.Numerics.Vector<float>(y[j..]) + vs * new System.Numerics.Vector<float>(row[j..])).CopyTo(y[j..]);
        for (; j < y.Length; j++) y[j] += s * row[j];
    }

    private static void Relu(Span<float> y)
    {
        for (int j = 0; j < y.Length; j++) if (y[j] < 0) y[j] = 0;
    }
}
