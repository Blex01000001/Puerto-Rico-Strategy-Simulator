"""Train an MLP value model on position dumps (PyTorch when installed, otherwise plain NumPy).

    python3 ml/train_mlp.py --out ml/models/4p-mlp-v2.json results/ml/4p-*.bin
    python3 ml/train_mlp.py --backend torch --device cuda ...      (GPU, e.g. on RunPod)

Data arguments may be files, wildcards or directories (as in train_lgbm.py). Importable: train(...) takes a progress
callback (used by the ML UI). Writes <out>, <out>.meta.json and <out>.check.txt. Stops early when the validation loss has
not improved for --patience epochs and keeps the best epoch.

Same label and validation split as train_lgbm.py (reward in [0,1], cross-entropy loss through a sigmoid,
held-out games). Network: standardised input -> hidden ReLU layers -> 1 output, Adam with L2, learning rate halved every
4 epochs. Both backends save the same JSON (format "mlp", read by MlpValueModel in Engine/Strategies/Mcts/ValueModel.cs),
so the engine does not care which one trained the model. As with LightGBM, the loss is only a sanity check; the model is
judged by MCTS win rates.
"""
import argparse
import json
import time

import numpy as np

import modelmeta
import positions

DEFAULTS = {"hidden": "256,128", "epochs": 12, "batch": 1024, "lr": 1e-3, "l2": 1e-5, "patience": 3,
            "valid": 0.1, "seed": 1, "backend": "auto", "device": "auto"}
LR_HALVING_EPOCHS = 4


def torch_available():
    try:
        import torch  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 - a broken install (e.g. missing CUDA libraries) counts as unavailable
        return False


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def forward(params, x):
    """NumPy forward pass; params = [(w [in, out], b [out]), ...]. Returns every layer's activation."""
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
    return preds, float(ce)


class Data:
    """Training rows kept as int16 (a float copy of millions of rows does not fit in memory), standardised per batch."""

    def __init__(self, data, valid_share, seed):
        x, reward, _, groups, self.names, self.metas = positions.load(data)
        valid = positions.split(groups, valid_share, seed)
        self.raw_valid = x[valid]
        self.xt, self.yt, self.yv = x[~valid], reward[~valid], reward[valid]
        del x
        s1 = np.zeros(self.xt.shape[1])
        s2 = np.zeros(self.xt.shape[1])
        for i in range(0, len(self.xt), 262144):
            c = self.xt[i:i + 262144].astype(np.float64)
            s1 += c.sum(axis=0)
            s2 += (c * c).sum(axis=0)
        n = len(self.xt)
        self.mean = (s1 / n).astype(np.float32)
        self.scale = np.sqrt(np.maximum(s2 / n - (s1 / n) ** 2, 0)).astype(np.float32)
        self.scale[self.scale < 1e-6] = 1.0
        self.xv = self.std(self.raw_valid)

    def std(self, a):
        return ((a.astype(np.float32) - self.mean) / self.scale).astype(np.float32)


class EarlyStop:
    def __init__(self, patience, log):
        self.patience, self.log = patience, log
        self.best = (np.inf, None, 0)
        self.curve = []

    def step(self, epoch, loss, params):
        """Records the epoch; returns True when training should stop."""
        self.curve.append(float(loss))
        if loss < self.best[0]:
            self.best = (loss, params(), epoch)
        elif epoch - self.best[2] >= self.patience:
            self.log(f"no improvement for {self.patience} epochs: stop, keep epoch {self.best[2]}")
            return True
        return False


def fit_numpy(d, sizes, o, rng, progress, log):
    params = [(rng.normal(0, np.sqrt(2.0 / sizes[i]), (sizes[i], sizes[i + 1])).astype(np.float32),
               np.zeros(sizes[i + 1], np.float32)) for i in range(len(sizes) - 1)]
    m = [(np.zeros_like(w), np.zeros_like(b)) for w, b in params]
    v = [(np.zeros_like(w), np.zeros_like(b)) for w, b in params]
    b1, b2, step = 0.9, 0.999, 0
    stop = EarlyStop(o["patience"], log)
    for epoch in range(1, o["epochs"] + 1):
        t0 = time.time()
        lr = o["lr"] * (0.5 ** ((epoch - 1) // LR_HALVING_EPOCHS))
        order = rng.permutation(len(d.xt))
        for start in range(0, len(order), o["batch"]):
            idx = order[start:start + o["batch"]]
            acts = forward(params, d.std(d.xt[idx]))
            # d(cross-entropy)/d(logit) = sigmoid(logit) - y
            grad = (sigmoid(acts[-1][:, 0]) - d.yt[idx])[:, None].astype(np.float32) / len(idx)
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
        preds, ce = evaluate(params, d.xv, d.yv)
        log(f"epoch {epoch}: valid cross-entropy {ce:.4f}, MSE {np.mean((preds - d.yv) ** 2):.4f}  ({time.time() - t0:.0f} s)")
        progress({"stage": "epoch", "epoch": epoch, "total": o["epochs"], "validLoss": ce})
        if stop.step(epoch, ce, lambda: [(w.copy(), b.copy()) for w, b in params]):
            break
    return stop, "cpu"


def fit_torch(d, sizes, o, rng, progress, log):
    import torch
    from torch import nn

    device = o["device"]
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(o["seed"])
    layers = []
    for i in range(len(sizes) - 1):
        layers.append(nn.Linear(sizes[i], sizes[i + 1]))
        if i < len(sizes) - 2:
            layers.append(nn.ReLU())
    net = nn.Sequential(*layers).to(device)
    for layer in net:
        if isinstance(layer, nn.Linear):  # He initialisation, zero bias (same as the NumPy backend)
            nn.init.kaiming_normal_(layer.weight, nonlinearity="relu")
            nn.init.zeros_(layer.bias)
    opt = torch.optim.Adam(net.parameters(), lr=o["lr"], weight_decay=o["l2"])
    sched = torch.optim.lr_scheduler.StepLR(opt, step_size=LR_HALVING_EPOCHS, gamma=0.5)
    loss_fn = nn.BCEWithLogitsLoss()  # soft labels in [0,1]: cross-entropy through a sigmoid
    xv = torch.from_numpy(d.xv).to(device)
    yv = torch.from_numpy(d.yv).to(device)

    def params():
        lin = [layer for layer in net if isinstance(layer, nn.Linear)]
        return [(layer.weight.detach().cpu().numpy().T.copy(), layer.bias.detach().cpu().numpy().copy()) for layer in lin]

    stop = EarlyStop(o["patience"], log)
    for epoch in range(1, o["epochs"] + 1):
        t0 = time.time()
        net.train()
        order = rng.permutation(len(d.xt))
        for start in range(0, len(order), o["batch"]):
            idx = np.sort(order[start:start + o["batch"]])  # sorted indices read the int16 array faster
            xb = torch.from_numpy(d.std(d.xt[idx])).to(device)
            yb = torch.from_numpy(d.yt[idx]).to(device)
            opt.zero_grad()
            loss = loss_fn(net(xb)[:, 0], yb)
            loss.backward()
            opt.step()
        sched.step()
        net.eval()
        with torch.no_grad():
            logits = torch.cat([net(xv[i:i + 65536])[:, 0] for i in range(0, len(xv), 65536)])
            ce = float(loss_fn(logits, yv))
            mse = float(((torch.sigmoid(logits) - yv) ** 2).mean())
        log(f"epoch {epoch}: valid cross-entropy {ce:.4f}, MSE {mse:.4f}  ({time.time() - t0:.0f} s, {device})")
        progress({"stage": "epoch", "epoch": epoch, "total": o["epochs"], "validLoss": ce})
        if stop.step(epoch, ce, params):
            break
    return stop, device


def train(data, out, progress=None, log=print, **options):
    """Trains and saves the model. progress(event: dict) gets {"stage": "loaded"|"epoch"|"done", ...}. Returns the meta."""
    o = {**DEFAULTS, **options}
    progress = progress or (lambda event: None)
    backend = o["backend"]
    if backend == "auto":
        backend = "torch" if torch_available() else "numpy"
    if backend == "torch" and not torch_available():
        raise RuntimeError("backend torch: PyTorch is not installed (pip install torch), use --backend numpy")
    if backend not in ("torch", "numpy"):
        raise ValueError(f"unknown backend {backend!r}")
    d = Data(data, o["valid"], o["seed"])
    log(f"{len(d.xt) + len(d.xv):,} rows, {len(d.names)} features; validation {len(d.xv):,} rows; backend {backend}")
    progress({"stage": "loaded", "rows": int(len(d.xt) + len(d.xv)), "validRows": int(len(d.xv)), "features": len(d.names)})

    rng = np.random.default_rng(o["seed"])
    hidden = [int(h) for h in str(o["hidden"]).split(",") if h.strip()]
    sizes = [len(d.names)] + hidden + [1]
    t_start = time.time()
    fit = fit_torch if backend == "torch" else fit_numpy
    stop, device = fit(d, sizes, o, rng, progress, log)
    seconds = time.time() - t_start

    params = stop.best[1]
    preds, _ = evaluate(params, d.xv, d.yv)  # the exported weights, evaluated the way the engine does
    rounds = d.raw_valid[:, d.names.index("round")].astype(np.float32)
    validation = modelmeta.validation_summary(preds, d.yv, d.yt.mean(), rounds)
    log(f"best epoch {stop.best[2]}: valid cross-entropy {validation['crossEntropy']:.4f}, MSE {validation['mse']:.4f} "
        f"(constant {validation['constantMse']:.4f}, R2 {validation['r2']:.3f})")
    model = {
        "format": "mlp",
        "features": d.names,
        "mean": d.mean.tolist(),
        "scale": d.scale.tolist(),
        "activation": "relu",
        "output": "sigmoid",
        # weights per output row (C# reads [out][in])
        "layers": [{"weights": w.T.tolist(), "bias": b.tolist()} for w, b in params],
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(model, f)
    np.savetxt(out + ".check.txt", np.column_stack([preds[:5], d.raw_valid[:5].astype(np.float32)]), fmt="%.9g")
    libraries = {"numpy": np.__version__}
    if backend == "torch":
        import torch
        libraries["torch"] = torch.__version__
    meta = modelmeta.write(
        out, "mlp", d.metas,
        params={"hidden": hidden, "epochs": o["epochs"], "batch": o["batch"], "lr": o["lr"], "lrHalvingEveryEpochs": LR_HALVING_EPOCHS,
                "l2": o["l2"], "patience": o["patience"], "valid_share": o["valid"], "seed": o["seed"],
                "optimizer": "adam", "loss": "cross_entropy", "backend": backend, "device": device},
        training={"seconds": round(seconds, 1), "epochsRun": len(stop.curve), "bestEpoch": stop.best[2],
                  "validLossCurve": [round(c, 6) for c in stop.curve]},
        validation=validation, top_features=[], libraries=libraries)
    progress({"stage": "done", "model": out, "validation": validation})
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", nargs="+", help="position dumps (.bin with .bin.json), wildcards or directories")
    ap.add_argument("--out", required=True, help="model file (.json)")
    ap.add_argument("--hidden", default=DEFAULTS["hidden"], help="hidden layer sizes, e.g. 256,128 (bigger = slower inference in MCTS)")
    ap.add_argument("--epochs", type=int, default=DEFAULTS["epochs"], help="maximum epochs")
    ap.add_argument("--batch", type=int, default=DEFAULTS["batch"])
    ap.add_argument("--lr", type=float, default=DEFAULTS["lr"], help="Adam learning rate (halved every 4 epochs)")
    ap.add_argument("--l2", type=float, default=DEFAULTS["l2"])
    ap.add_argument("--patience", type=int, default=DEFAULTS["patience"], help="stop after this many epochs without improvement")
    ap.add_argument("--valid", type=float, default=DEFAULTS["valid"], help="share of games held out")
    ap.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    ap.add_argument("--backend", default=DEFAULTS["backend"], choices=["auto", "torch", "numpy"], help="auto = torch when installed")
    ap.add_argument("--device", default=DEFAULTS["device"], help="torch device: auto (cuda when available), cpu, cuda")
    a = ap.parse_args()
    train(a.data, a.out, hidden=a.hidden, epochs=a.epochs, batch=a.batch, lr=a.lr, l2=a.l2, patience=a.patience,
          valid=a.valid, seed=a.seed, backend=a.backend, device=a.device)


if __name__ == "__main__":
    main()
