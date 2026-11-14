"""Regenerates the tiny LightGBM fixture used by Tests/ValueModelTests.cs (C# vs Python parity).

    python3 ml/make_test_fixture.py results/ml/4p-hand-a.bin

Needed after the feature list changes (ValueFeatures.Version): the fixture's feature names must match the engine.
Writes Tests/Data/tiny-lgbm.txt (6 trees, 8 leaves) and Tests/Data/tiny-lgbm.check.txt (python prediction + features, 40 rows).
"""
import os
import sys

import lightgbm as lgb
import numpy as np

import positions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    x, reward, _, _, names, _ = positions.load([sys.argv[1]])
    n = min(50000, len(x))
    x, reward = x[:n].astype(np.float32), reward[:n]
    params = {"objective": "cross_entropy", "num_leaves": 8, "verbose": -1, "deterministic": True, "seed": 1, "num_threads": 1}
    booster = lgb.train(params, lgb.Dataset(x, reward, feature_name=names), 6)
    out = os.path.join(ROOT, "Tests", "Data", "tiny-lgbm.txt")
    booster.save_model(out)
    idx = np.arange(0, n, 997)[:40]
    np.savetxt(os.path.join(ROOT, "Tests", "Data", "tiny-lgbm.check.txt"), np.column_stack([booster.predict(x[idx]), x[idx]]), fmt="%.9g")
    print(f"wrote {out} (+ .check.txt)")


if __name__ == "__main__":
    main()
