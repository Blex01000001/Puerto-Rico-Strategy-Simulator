import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import positions  # noqa: E402

NAMES = ["players", "round", "p0_score", "p1_score", "p2_score", "p3_score"]


def write_dump(path, games=40, per_game=5, players=4, names=NAMES, seed=0, **meta_overrides):
    """Synthetic dump in the Runner's format; the label follows p0_score - p1_score so models can learn it."""
    rng = np.random.default_rng(seed)
    dtype = positions.record_dtype(len(names))
    rows = games * per_game * players
    data = np.zeros(rows, dtype=dtype)
    data["game"] = np.repeat(np.arange(games), per_game * players)
    x = rng.integers(0, 40, size=(rows, len(names)))
    x[:, 0] = players
    x[:, 1] = rng.integers(1, 18, size=rows)
    data["x"] = x
    diff = (x[:, 2] - x[:, 3]) / 10.0
    data["reward"] = 1 / (1 + np.exp(-diff))
    data["win"] = (diff > 0).astype(np.float32)
    data.tofile(path)
    meta = {
        "format": "pr-positions", "formatVersion": 1, "status": "completed", "featureVersion": 1,
        "recordBytes": dtype.itemsize, "featureCount": len(names), "featureNames": names, "rows": rows,
        "positions": rows // players, "games": games, "rate": 0.05, "name": os.path.basename(path), "players": players,
        "seed": seed, "seatOrder": "Random", "seats": [{"id": "a", "strategy": "mcts", "params": {"valueModel": "ml/models/x.txt"}}],
    }
    meta.update(meta_overrides)
    with open(path + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return path


@pytest.fixture
def dump(tmp_path):
    return lambda name="a.bin", **kw: write_dump(str(tmp_path / name), **kw)
