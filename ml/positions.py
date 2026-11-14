"""Reads position dumps written by `Runner --dump-positions` (Engine/Simulation/PositionDump.cs).

The format is defined on the C# side; this module only follows it and refuses files it does not understand.
"""
import glob
import json
import os

import numpy as np

FORMAT = "pr-positions"
FORMAT_VERSION = 1


def expand(paths):
    """Expands wildcards and directories (Windows shells pass `*.bin` through unexpanded).

    A directory stands for every `*.bin` inside it. Returns a sorted, de-duplicated list; raises if a pattern matches nothing.
    """
    out = []
    for p in paths:
        if os.path.isdir(p):
            matches = sorted(glob.glob(os.path.join(p, "*.bin")))
        elif any(c in p for c in "*?["):
            matches = sorted(glob.glob(p))
        else:
            matches = [p]
        if not matches:
            raise ValueError(f"no position dump matches '{p}'")
        out.extend(matches)
    seen = set()
    return [p for p in out if not (p in seen or seen.add(p))]


def read_meta(path):
    """Metadata of one dump (`<path>.json`), checked for format and version."""
    meta_path = path + ".json"
    if not os.path.exists(meta_path):
        raise ValueError(f"{path}: metadata {meta_path} is missing (an interrupted dump from an old Runner cannot be read)")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("format") != FORMAT:
        raise ValueError(f"{path}: not a position dump (format {meta.get('format')!r})")
    if meta.get("formatVersion") != FORMAT_VERSION:
        raise ValueError(f"{path}: format version {meta.get('formatVersion')}, this reader understands {FORMAT_VERSION}")
    if len(meta["featureNames"]) != meta["featureCount"]:
        raise ValueError(f"{path}: featureNames and featureCount disagree")
    meta.setdefault("status", "completed")  # dumps written before the status field were always complete
    return meta


def record_dtype(n_features):
    return np.dtype([("reward", "<f4"), ("win", "<f4"), ("game", "<i4"), ("x", "<i2", (n_features,))])


def load(paths):
    """Returns (X int16 [rows, F], reward float32, win float32, group int64, feature_names, metas).

    All files must share the feature list, feature version and player count. group = (file index << 32) | game index,
    so a train/validation split by group never puts positions of the same game on both sides.
    """
    paths = expand(paths)
    xs, rs, ws, gs, metas = [], [], [], [], []
    first = None
    for fi, path in enumerate(paths):
        meta = read_meta(path)
        if first is None:
            first = meta
        else:
            for key in ("featureVersion", "players"):
                if meta[key] != first[key]:
                    raise ValueError(f"{path}: {key} {meta[key]} differs from {paths[0]} ({first[key]})")
            if meta["featureNames"] != first["featureNames"]:
                raise ValueError(f"{path}: feature list differs from {paths[0]}")
        dtype = record_dtype(meta["featureCount"])
        if dtype.itemsize != meta["recordBytes"]:
            raise ValueError(f"{path}: record size {meta['recordBytes']} does not match the layout ({dtype.itemsize})")
        if os.path.getsize(path) != meta["rows"] * dtype.itemsize:
            raise ValueError(f"{path}: size does not match {meta['rows']} rows")
        data = np.fromfile(path, dtype=dtype)
        xs.append(data["x"])
        rs.append(data["reward"])
        ws.append(data["win"])
        gs.append((np.int64(fi) << 32) | data["game"].astype(np.int64))
        metas.append({"path": path, **meta})
    return np.concatenate(xs), np.concatenate(rs), np.concatenate(ws), np.concatenate(gs), first["featureNames"], metas


def split(groups, valid_share, seed):
    """Boolean mask of validation rows, chosen by game."""
    uniq = np.unique(groups)
    rng = np.random.default_rng(seed)
    valid = rng.choice(uniq, size=max(1, int(len(uniq) * valid_share)), replace=False)
    return np.isin(groups, valid)
