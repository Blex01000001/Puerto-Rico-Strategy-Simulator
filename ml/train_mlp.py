"""Train an MLP value model on position dumps (plain NumPy: no PyTorch needed).

    python3 ml/train_mlp.py --out ml/models/4p-mlp-v1.json results/ml/4p-*.bin

Data arguments may be files, wildcards or directories (as in train_lgbm.py). Importable: train(...) takes a progress
callback (used by the ML UI). Writes <out>, <out>.meta.json and <out>.check.txt. Stops early when the validation loss has
not improved for --patience epochs and keeps the best epoch.

Same label and validation split as train_lgbm.py (reward in [0,1], cross-entropy loss through a sigmoid,
held-out games). Network: standardised input -> hidden ReLU layers -> 1 output. Saved as JSON
(format "mlp", read by MlpValueModel in Engine/Strategies/Mcts/ValueModel.cs). As with LightGBM, the loss is only a
sanity check; the model is judged by MCTS win rates.
"""
import argparse
import json
import time

import numpy as np

import modelmeta
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


DEFAULTS = {"hidden": "256,128", "epochs": 12, "batch": 1024, "lr": 1e-3, "l2": 1e-5, "patience": 3,
            "valid": 0.1, "seed": 1}


def train(data, out, progress=None, log=print, **options):
    """Trains and saves the model. progress(event: dict) gets {"stage": "loaded"|"epoch"|"done", ...}. Returns the meta."""
    o = {**DEFAULTS, **options}
    progress = progress or (lambda event: None)
    x, reward, _, groups, names, metas = positions.load(data)
    valid = positions.split(groups, o["valid"], o["seed"])
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
    log(f"{len(xt) + len(xv):,} rows, {len(names)} features; validation {len(xv):,} rows")
    progress({"stage": "loaded", "rows": int(len(xt) + len(xv)), "validRows": int(len(xv)), "features": len(names)})

    rng = np.random.default_rng(o["seed"])
    hidden = [int(h) for h in str(o["hidden"]).split(",") if h.strip()]
    sizes = [len(names)] + hidden + [1]
    params = [(rng.normal(0, np.sqrt(2.0 / sizes[i]), (sizes[i], sizes[i + 1])).astype(np.float32),
               np.zeros(sizes[i + 1], np.float32)) for i in range(len(sizes) - 1)]
    m = [(np.zeros_like(w), np.zeros_like(b)) for w, b in params]
    v = [(np.zeros_like(w), np.zeros_like(b)) for w, b in params]
    b1, b2, step = 0.9, 0.999, 0
    best = (np.inf, None, 0)
    curve = []
    t_start = time.time()
    for epoch in range(o["epochs"]):
        t0 = time.time()
        lr = o["lr"] * (0.5 ** (epoch // 4))
        order = rng.permutation(len(xt))
        for start in range(0, len(order), o["batch"]):
            idx = order[start:start + o["batch"]]
            acts = forward(params, std(xt[idx]))
            # d(cross-entropy)/d(logit) = sigmoid(logit) - y
            grad = (sigmoid(acts[-1][:, 0]) - yt[idx])[:, None].astype(np.float32) / len(idx)
            step += 1
            for i in range(len(params) - 1, -1, -1):
                w, b = params[i]
                gw = acts[i].T @ grad + o["l2"] * w
                gb = grad.sum(axis=0)
                if i > 0:
                    grad = (grad @ w.T) * (acts[i] > 0)
                mw, mb = m[i]
                vw, vb = v[i]
                mw = b1 * mw + (1 - b1) * gw
                mb = b1 * mb + (1 - b1) * gb
                vw = b2 * vw + (1 - b2) * gw * gw
                vb = b2 * vb + (1 - b2) * gb * gb
                m[i], v[i] = (mw, mb), (vw, vb)
                corr = np.sqrt(1 - b2 ** step) / (1 - b1 ** step)
                params[i] = (w - lr * corr * mw / (np.sqrt(vw) + 1e-8), b - lr * corr * mb / (np.sqrt(vb) + 1e-8))
        preds, ce = evaluate(params, xv, yv)
        curve.append(float(ce))
        log(f"epoch {epoch + 1}: valid cross-entropy {ce:.4f}, MSE {np.mean((preds - yv) ** 2):.4f}  ({time.time() - t0:.0f} s)")
        progress({"stage": "epoch", "epoch": epoch + 1, "total": o["epochs"], "validLoss": float(ce)})
        if ce < best[0]:
            best = (ce, [(w.copy(), b.copy()) for w, b in params], epoch + 1)
        elif epoch + 1 - best[2] >= o["patience"]:
            log(f"no improvement for {o['patience']} epochs: stop, keep epoch {best[2]}")
            break
    seconds = time.time() - t_start

    params = best[1]
    preds, _ = evaluate(params, xv, yv)
    rounds = raw_valid[:, names.index("round")].astype(np.float32)
    validation = modelmeta.validation_summary(preds, yv, yt.mean(), rounds)
    log(f"best epoch {best[2]}: valid cross-entropy {validation['crossEntropy']:.4f}, MSE {validation['mse']:.4f} "
        f"(constant {validation['constantMse']:.4f}, R2 {validation['r2']:.3f})")
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
    with open(out, "w", encoding="utf-8") as f:
        json.dump(model, f)
    np.savetxt(out + ".check.txt", np.column_stack([preds[:5], raw_valid[:5].astype(np.float32)]), fmt="%.9g")
    meta = modelmeta.write(
        out, "mlp", metas,
        params={"hidden": hidden, "epochs": o["epochs"], "batch": o["batch"], "lr": o["lr"], "lrHalvingEveryEpochs": 4,
                "l2": o["l2"], "patience": o["patience"], "valid_share": o["valid"], "seed": o["seed"],
                "optimizer": "adam", "loss": "cross_entropy"},
        training={"seconds": round(seconds, 1), "epochsRun": len(curve), "bestEpoch": best[2],
                  "validLossCurve": [round(c, 6) for c in curve]},
        validation=validation, top_features=[],
        libraries={"numpy": np.__version__})
    progress({"stage": "done", "model": out, "validation": validation})
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", nargs="+", help="position dumps (.bin with .bin.json), wildcards or directories")
    ap.add_argument("--out", required=True, help="model file (.json)")
    ap.add_argument("--hidden", default=DEFAULTS["hidden"], help="hidden layer sizes, e.g. 256,128")
    ap.add_argument("--epochs", type=int, default=DEFAULTS["epochs"], help="maximum epochs")
    ap.add_argument("--batch", type=int, default=DEFAULTS["batch"])
    ap.add_argument("--lr", type=float, default=DEFAULTS["lr"], help="Adam learning rate (halved every 4 epochs)")
    ap.add_argument("--l2", type=float, default=DEFAULTS["l2"])
    ap.add_argument("--patience", type=int, default=DEFAULTS["patience"], help="stop after this many epochs without improvement")
    ap.add_argument("--valid", type=float, default=DEFAULTS["valid"], help="share of games held out")
    ap.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    a = ap.parse_args()
    train(a.data, a.out, hidden=a.hidden, epochs=a.epochs, batch=a.batch, lr=a.lr, l2=a.l2,
          patience=a.patience, valid=a.valid, seed=a.seed)


if __name__ == "__main__":
    main()
