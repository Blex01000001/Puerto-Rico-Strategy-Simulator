"""Train a LightGBM value model on position dumps.

    python3 ml/train_lgbm.py --out ml/models/4p-v1.txt results/ml/4p-*.bin

Label = the seat's final MCTS reward (0.6 x win + 0.4 x rank score), objective cross_entropy
(labels in [0,1], output through a sigmoid). The engine evaluates the saved text model itself
(Engine/Strategies/Mcts/ValueModel.cs), so only numerical splits are used. Validation is split by game.
MSE is printed only as a sanity check: the model is judged by MCTS win rates, not by its loss.
"""
import argparse
import time

import lightgbm as lgb
import numpy as np

import positions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="+", help="position dump files (.bin, each with its .bin.json)")
    ap.add_argument("--out", required=True, help="model file (LightGBM text format, .txt)")
    ap.add_argument("--rounds", type=int, default=400)
    ap.add_argument("--leaves", type=int, default=63)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--min-leaf", type=int, default=200)
    ap.add_argument("--valid", type=float, default=0.1, help="share of games held out")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--threads", type=int, default=0)
    args = ap.parse_args()

    x, reward, win, groups, names = positions.load(args.data)
    valid = positions.split(groups, args.valid, args.seed)
    print(f"{len(x):,} rows, {len(names)} features, {len(np.unique(groups)):,} games; validation {valid.sum():,} rows")

    params = {
        "objective": "cross_entropy",
        "learning_rate": args.lr,
        "num_leaves": args.leaves,
        "min_data_in_leaf": args.min_leaf,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "seed": args.seed,
        "deterministic": True,
        "num_threads": args.threads,
        "verbose": -1,
    }
    xf = x.astype(np.float32)
    train = lgb.Dataset(xf[~valid], reward[~valid], feature_name=names, free_raw_data=False)
    dvalid = lgb.Dataset(xf[valid], reward[valid], reference=train)
    t0 = time.time()
    booster = lgb.train(params, train, args.rounds, valid_sets=[dvalid],
                        callbacks=[lgb.log_evaluation(50), lgb.early_stopping(30)])
    print(f"trained {booster.num_trees()} trees in {time.time() - t0:.0f} s")

    pred = booster.predict(xf[valid])
    base = np.full_like(pred, reward[~valid].mean())
    mse, base_mse = np.mean((pred - reward[valid]) ** 2), np.mean((base - reward[valid]) ** 2)
    print(f"validation MSE {mse:.4f} (constant {base_mse:.4f}, R2 {1 - mse / base_mse:.3f})")
    rounds = xf[valid][:, names.index("round")]
    for lo, hi in [(1, 4), (5, 8), (9, 12), (13, 99)]:
        m = (rounds >= lo) & (rounds <= hi)
        if m.any():
            print(f"  rounds {lo:>2}-{hi:<2}: MSE {np.mean((pred[m] - reward[valid][m]) ** 2):.4f}  n={m.sum():,}")

    booster.save_model(args.out)
    # 5 rows the C# side must reproduce (Tests / tools can compare against them)
    np.savetxt(args.out + ".check.txt", np.column_stack([booster.predict(xf[valid][:5]), xf[valid][:5]]), fmt="%.9g")
    imp = sorted(zip(booster.feature_importance("gain"), names), reverse=True)[:15]
    print("top features (gain):", ", ".join(f"{n}" for _, n in imp))


if __name__ == "__main__":
    main()
