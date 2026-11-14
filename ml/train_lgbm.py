"""Train a LightGBM value model on position dumps.

    python3 ml/train_lgbm.py --out ml/models/4p-v1.txt results/ml/4p-*.bin

Label = the seat's final MCTS reward (0.6 x win + 0.4 x rank score), objective cross_entropy
(labels in [0,1], output through a sigmoid). The engine evaluates the saved text model itself
(Engine/Strategies/Mcts/ValueModel.cs), so only numerical splits are used. Validation is split by game.
Writes <out> (model), <out>.meta.json (parameters, data, validation) and <out>.check.txt (rows for the C# parity check).
The loss is only a sanity check: the model is judged by MCTS win rates.

Data arguments may be files, wildcards (expanded here, also on Windows) or directories (every *.bin inside).
Importable: train(...) takes a progress callback (used by the ML UI).
"""
import argparse
import time

import lightgbm as lgb
import numpy as np

import modelmeta
import positions

DEFAULTS = {"rounds": 400, "leaves": 63, "lr": 0.05, "min_leaf": 200, "feature_fraction": 0.8,
            "bagging_fraction": 0.8, "valid": 0.1, "seed": 1, "threads": 0, "early_stopping": 30}


def train(data, out, progress=None, log=print, **options):
    """Trains and saves the model. progress(event: dict) gets {"stage": "loaded"|"iteration"|"done", ...}.

    Returns the meta dictionary that was written to <out>.meta.json.
    """
    o = {**DEFAULTS, **options}
    progress = progress or (lambda event: None)
    x, reward, _, groups, names, metas = positions.load(data)
    valid = positions.split(groups, o["valid"], o["seed"])
    log(f"{len(x):,} rows, {len(names)} features, {len(np.unique(groups)):,} games; validation {valid.sum():,} rows")
    progress({"stage": "loaded", "rows": int(len(x)), "validRows": int(valid.sum()), "features": len(names)})

    params = {
        "objective": "cross_entropy",
        "learning_rate": o["lr"],
        "num_leaves": o["leaves"],
        "min_data_in_leaf": o["min_leaf"],
        "feature_fraction": o["feature_fraction"],
        "bagging_fraction": o["bagging_fraction"],
        "bagging_freq": 1,
        "seed": o["seed"],
        "deterministic": True,
        "num_threads": o["threads"],
        "verbose": -1,
    }
    # float copies are made per part and the training copy is freed once LightGBM has binned it
    # (one float copy of all rows plus a sliced copy did not fit in 15 GB at 3.4 million rows)
    xv = x[valid].astype(np.float32)
    yt, yv = reward[~valid], reward[valid]
    train_set = lgb.Dataset(x[~valid].astype(np.float32), yt, feature_name=names, params=params, free_raw_data=True)
    del x
    train_set.construct()
    valid_set = lgb.Dataset(xv, yv, reference=train_set, params=params)
    curve = []

    def record(env):
        loss = env.evaluation_result_list[0][2]
        curve.append(loss)
        progress({"stage": "iteration", "iteration": env.iteration + 1, "total": o["rounds"], "validLoss": loss})
        if (env.iteration + 1) % 50 == 0:
            log(f"[{env.iteration + 1}] valid cross_entropy {loss:.6f}")

    t0 = time.time()
    booster = lgb.train(params, train_set, o["rounds"], valid_sets=[valid_set],
                        callbacks=[record, lgb.early_stopping(o["early_stopping"], verbose=False)])
    seconds = time.time() - t0
    log(f"trained {booster.num_trees()} trees in {seconds:.0f} s")

    pred = booster.predict(xv)
    rounds = xv[:, names.index("round")]
    validation = modelmeta.validation_summary(pred, yv, yt.mean(), rounds)
    log(f"validation MSE {validation['mse']:.4f} (constant {validation['constantMse']:.4f}, R2 {validation['r2']:.3f})")
    for st in validation["byRound"]:
        log(f"  rounds {st['rounds']:<6}: MSE {st['mse']:.4f}  n={st['rows']:,}")

    booster.save_model(out)
    # rows the C# side must reproduce (see Tests/ValueModelTests and ml/README.md)
    np.savetxt(out + ".check.txt", np.column_stack([pred[:5], xv[:5]]), fmt="%.9g")
    gains = booster.feature_importance("gain")
    top = [{"name": n, "gain": float(g)} for g, n in sorted(zip(gains, names), reverse=True)[:30]]
    log("top features (gain): " + ", ".join(t["name"] for t in top[:15]))
    meta = modelmeta.write(
        out, "lightgbm", metas,
        params={**params, "num_boost_round": o["rounds"], "early_stopping_rounds": o["early_stopping"], "valid_share": o["valid"]},
        training={"seconds": round(seconds, 1), "iterations": booster.num_trees(), "bestIteration": booster.best_iteration,
                  "validLossCurve": [round(v, 6) for v in curve]},
        validation=validation, top_features=top,
        libraries={"lightgbm": lgb.__version__, "numpy": np.__version__})
    progress({"stage": "done", "model": out, "validation": validation})
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", nargs="+", help="position dumps (.bin with .bin.json), wildcards or directories")
    ap.add_argument("--out", required=True, help="model file (LightGBM text format, .txt)")
    ap.add_argument("--rounds", type=int, default=DEFAULTS["rounds"], help="boosting rounds (trees)")
    ap.add_argument("--leaves", type=int, default=DEFAULTS["leaves"], help="leaves per tree")
    ap.add_argument("--lr", type=float, default=DEFAULTS["lr"], help="learning rate")
    ap.add_argument("--min-leaf", type=int, default=DEFAULTS["min_leaf"], help="minimum rows per leaf")
    ap.add_argument("--feature-fraction", type=float, default=DEFAULTS["feature_fraction"])
    ap.add_argument("--bagging-fraction", type=float, default=DEFAULTS["bagging_fraction"])
    ap.add_argument("--early-stopping", type=int, default=DEFAULTS["early_stopping"], help="stop after this many rounds without improvement")
    ap.add_argument("--valid", type=float, default=DEFAULTS["valid"], help="share of games held out")
    ap.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    ap.add_argument("--threads", type=int, default=DEFAULTS["threads"], help="0 = all cores")
    a = ap.parse_args()
    train(a.data, a.out, rounds=a.rounds, leaves=a.leaves, lr=a.lr, min_leaf=a.min_leaf,
          feature_fraction=a.feature_fraction, bagging_fraction=a.bagging_fraction,
          early_stopping=a.early_stopping, valid=a.valid, seed=a.seed, threads=a.threads)


if __name__ == "__main__":
    main()
