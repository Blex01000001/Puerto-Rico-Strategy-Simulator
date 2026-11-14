"""Reads position dumps written by `Runner --dump-positions` (Engine/Simulation/PositionDump.cs)."""
import json
import os

import numpy as np


def load(paths):
    """Returns (X int16 [rows, F], reward float32, win float32, group int64, feature_names).

    group = (file index << 32) | game index, so a train/validation split by group never puts
    positions of the same game on both sides.
    """
    xs, rs, ws, gs = [], [], [], []
    names = None
    for fi, path in enumerate(paths):
        with open(path + ".json", encoding="utf-8") as f:
            meta = json.load(f)
        if meta["format"] != "pr-positions" or meta["formatVersion"] != 1:
            raise ValueError(f"{path}: unknown format")
        if names is None:
            names = meta["featureNames"]
        elif names != meta["featureNames"]:
            raise ValueError(f"{path}: feature list differs from {paths[0]}")
        n_feat = meta["featureCount"]
        dtype = np.dtype([("reward", "<f4"), ("win", "<f4"), ("game", "<i4"), ("x", "<i2", (n_feat,))])
        if os.path.getsize(path) != meta["rows"] * dtype.itemsize:
            raise ValueError(f"{path}: size does not match {meta['rows']} rows")
        data = np.fromfile(path, dtype=dtype)
        xs.append(data["x"])
        rs.append(data["reward"])
        ws.append(data["win"])
        gs.append((np.int64(fi) << 32) | data["game"].astype(np.int64))
    return np.concatenate(xs), np.concatenate(rs), np.concatenate(ws), np.concatenate(gs), names


def split(groups, valid_share, seed):
    """Boolean mask of validation rows, chosen by game."""
    uniq = np.unique(groups)
    rng = np.random.default_rng(seed)
    valid = rng.choice(uniq, size=max(1, int(len(uniq) * valid_share)), replace=False)
    return np.isin(groups, valid)
