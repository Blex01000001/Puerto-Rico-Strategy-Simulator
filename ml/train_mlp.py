"""Train an MLP value model on position dumps (plain NumPy: no PyTorch needed).

    python3 ml/train_mlp.py --out ml/models/4p-mlp-v1.json results/ml/4p-*.bin

Same label and validation split as train_lgbm.py (reward in [0,1], cross-entropy loss through a sigmoid,
held-out games). Network: standardised input -> hidden ReLU layers -> 1 output. Saved as JSON
(format "mlp", read by MlpValueModel in Engine/Strategies/Mcts/ValueModel.cs). As with LightGBM, the loss is only a
sanity check; the model is judged by MCTS win rates.
"""
import argparse
import json
import time

import numpy as np

import positions


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def forward(params, x):
    acts = [x]
    h = x
    for i, (w, b) in enumerate(params):
        z = h @ w + b
        h = z if i == len(params) - 1 else np.maximum(z, 0)
        acts.append(h)
    return acts


def evaluate(params, x, y, batch=65536):
    preds = np.concatenate([sigmoid(forward(params, x[i:i + batch])[-1][:, 0]) for i in range(0, len(x), batch)])
    eps = 1e-7
    ce = -np.mean(y * np.log(preds + eps) + (1 - y) * np.log(1 - preds + eps))
    return preds, ce


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="+")
    ap.add_argument("--out", required=True, help="model file (.json)")
    ap.add_argument("--hidden", default="256,128", help="hidden layer sizes")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--l2", type=float, default=1e-5)
    ap.add_argument("--valid", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    x, reward, _, groups, names = positions.load(args.data)
    valid = positions.split(groups, args.valid, args.seed)
    # keep the training features as int16 (a float copy of millions of rows does not fit in memory); standardise per batch
    raw_valid = x[valid]
    xt, yt, yv = x[~valid], reward[~valid], reward[valid]
    del x
    s1 = np.zeros(xt.shape[1])
    s2 = np.zeros(xt.shape[1])
    for i in range(0, len(xt), 262144):
        c = xt[i:i + 262144].astype(np.float64)
        s1 += c.sum(axis=0)
        s2 += (c * c).sum(axis=0)
    mean = (s1 / len(xt)).astype(np.float32)
    scale = np.sqrt(np.maximum(s2 / len(xt) - (s1 / len(xt)) ** 2, 0)).astype(np.float32)
    scale[scale < 1e-6] = 1.0

    def std(a):
        return ((a.astype(np.float32) - mean) / scale).astype(np.float32)

    xv = std(raw_valid)
    print(f"{len(xt) + len(xv):,} rows, {len(names)} features; validation {len(xv):,} rows")

    rng = np.random.default_rng(args.seed)
    sizes = [len(names)] + [int(h) for h in args.hidden.split(",") if h] + [1]
    params = [(rng.normal(0, np.sqrt(2.0 / sizes[i]), (sizes[i], sizes[i + 1])).astype(np.float32),
               np.zeros(sizes[i + 1], np.float32)) for i in range(len(sizes) - 1)]
    m = [(np.zeros_like(w), np.zeros_like(b)) for w, b in params]
    v = [(np.zeros_like(w), np.zeros_like(b)) for w, b in params]
    b1, b2, step = 0.9, 0.999, 0
    best = (np.inf, None)
    for epoch in range(args.epochs):
        t0 = time.time()
        lr = args.lr * (0.5 ** (epoch // 4))
        order = rng.permutation(len(xt))
        for start in range(0, len(order), args.batch):
            idx = order[start:start + args.batch]
            acts = forward(params, std(xt[idx]))
            # d(cross-entropy)/d(logit) = sigmoid(logit) - y
            grad = (sigmoid(acts[-1][:, 0]) - yt[idx])[:, None].astype(np.float32) / len(idx)
            step += 1
            for i in range(len(params) - 1, -1, -1):
                w, b = params[i]
                gw = acts[i].T @ grad + args.l2 * w
                gb = grad.sum(axis=0)
                if i > 0:
                    grad = (grad @ w.T) * (acts[i] > 0)
                mw, mb = m[i]
                vw, vb = v[i]
                mw = b1 * mw + (1 - b1) * gw; mb = b1 * mb + (1 - b1) * gb
                vw = b2 * vw + (1 - b2) * gw * gw; vb = b2 * vb + (1 - b2) * gb * gb
                m[i], v[i] = (mw, mb), (vw, vb)
                corr = np.sqrt(1 - b2 ** step) / (1 - b1 ** step)
                params[i] = (w - lr * corr * mw / (np.sqrt(vw) + 1e-8), b - lr * corr * mb / (np.sqrt(vb) + 1e-8))
        preds, ce = evaluate(params, xv, yv)
        mse = np.mean((preds - yv) ** 2)
        print(f"epoch {epoch + 1}: valid cross-entropy {ce:.4f}, MSE {mse:.4f}  ({time.time() - t0:.0f} s)")
        if ce < best[0]:
            best = (ce, [(w.copy(), b.copy()) for w, b in params])

    params = best[1]
    preds, ce = evaluate(params, xv, yv)
    base_mse = np.mean((yt.mean() - yv) ** 2)
    print(f"best: valid cross-entropy {ce:.4f}, MSE {np.mean((preds - yv) ** 2):.4f} (constant {base_mse:.4f})")
    model = {
        "format": "mlp",
        "features": names,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "activation": "relu",
        "output": "sigmoid",
        # weights per output row (C# reads [out][in])
        "layers": [{"weights": w.T.tolist(), "bias": b.tolist()} for w, b in params],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(model, f)
    raw = raw_valid[:5].astype(np.float32)
    np.savetxt(args.out + ".check.txt", np.column_stack([preds[:5], raw]), fmt="%.9g")


if __name__ == "__main__":
    main()
