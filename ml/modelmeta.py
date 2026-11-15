"""`<model>.meta.json`: how a model was trained (parameters, data, validation) and, later, how it played.

Written next to every model by train_lgbm.py / train_mlp.py. The engine never reads it (models are checked by their
feature names); it is for people, the ML UI and later comparisons. Win rates from MCTS matches are the real verdict;
the validation numbers are only a sanity check.
"""
import datetime
import json
import os
import platform

import numpy as np

FORMAT = "pr-model-meta"
FORMAT_VERSION = 1

# Official models live in ml/models (tracked by git). Everything the ML UI makes on this machine goes to the local
# workspace ml/local (ignored by git): models, data configs, match configs, and the match results of official models
# (kept beside, never written into a tracked .meta.json, so running a match does not show up as a git change).
ML_DIR = os.path.dirname(os.path.abspath(__file__))
OFFICIAL_MODELS = os.path.join(ML_DIR, "models")
LOCAL_DIR = os.path.join(ML_DIR, "local")


def local_models_dir():
    return os.path.join(LOCAL_DIR, "models")


def local_records_dir():
    return os.path.join(LOCAL_DIR, "match-records")


def is_official(model_path):
    return os.path.dirname(os.path.abspath(model_path)) == os.path.abspath(OFFICIAL_MODELS)


def _records_path(model_path):
    return os.path.join(local_records_dir(), os.path.basename(model_path) + ".matches.json")


def _local_records(model_path):
    try:
        with open(_records_path(model_path), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def data_summary(metas):
    """Per dump file: what it is and where it came from."""
    return [{
        "path": m["path"].replace(os.sep, "/"),
        "rows": m["rows"],
        "games": m["games"],
        "status": m["status"],
        "rate": m["rate"],
        "source": m.get("name") or os.path.basename(m["path"]),
        "seed": m["seed"],
        "strategies": [s.get("strategy") for s in m.get("seats", [])],
        "valueModels": sorted({(s.get("params") or {}).get("valueModel") for s in m.get("seats", [])} - {None}),
    } for m in metas]


def validation_summary(pred, label, train_mean, rounds):
    """Cross-entropy, MSE, R2 against a constant, and MSE by game stage."""
    eps = 1e-7
    p = np.clip(pred, eps, 1 - eps)
    mse = float(np.mean((pred - label) ** 2))
    base = float(np.mean((train_mean - label) ** 2))
    stages = []
    for lo, hi in [(1, 4), (5, 8), (9, 12), (13, 999)]:
        m = (rounds >= lo) & (rounds <= hi)
        if m.any():
            stages.append({"rounds": f"{lo}-{hi if hi < 999 else ''}", "rows": int(m.sum()),
                           "mse": float(np.mean((pred[m] - label[m]) ** 2))})
    return {
        "rows": int(len(label)),
        "crossEntropy": float(-np.mean(label * np.log(p) + (1 - label) * np.log(1 - p))),
        "mse": mse,
        "constantMse": base,
        "r2": 1 - mse / base if base > 0 else 0.0,
        "byRound": stages,
    }


def environment(**libraries):
    return {"python": platform.python_version(), "machine": platform.machine(), "system": platform.system(),
            **{k: v for k, v in libraries.items()}}


def write(model_path, kind, metas, params, training, validation, top_features, libraries):
    meta = {
        "format": FORMAT,
        "formatVersion": FORMAT_VERSION,
        "model": os.path.basename(model_path),
        "kind": kind,
        "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "players": metas[0]["players"],
        "featureVersion": metas[0]["featureVersion"],
        "featureCount": metas[0]["featureCount"],
        "data": data_summary(metas),
        "params": params,
        "training": training,
        "validation": validation,
        "topFeatures": top_features,
        "environment": environment(**libraries),
        "matches": [],  # MCTS win rates, appended by the ML UI's match page (phase 2)
    }
    with open(model_path + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return meta


def read(model_path, include_local=True):
    """The model's metadata; for an official model also the matches recorded on this machine (marked "local": true)."""
    with open(model_path + ".meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("format") != FORMAT or meta.get("formatVersion") != FORMAT_VERSION:
        raise ValueError(f"{model_path}.meta.json: unknown format")
    if include_local and is_official(model_path):
        mine = {m["result"] for m in meta.get("matches", [])}
        meta["matches"] = meta.get("matches", []) + [{**m, "local": True} for m in _local_records(model_path) if m["result"] not in mine]
    return meta


def match_entry(result_path, model_path):
    """Summary of one Runner result file for the seat that used this model (MCTS valueModel)."""
    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)
    name = os.path.basename(model_path)
    cfg = result["config"]
    seats = {s["id"]: s for s in cfg["seats"]}
    mine = [s for s in cfg["seats"] if os.path.basename(str((s.get("params") or {}).get("valueModel", ""))) == name]
    if not mine:
        raise ValueError(f"{result_path}: no seat uses {name}")
    summary = {s["seatId"]: s for s in result["summary"]}
    me = summary[mine[0]["id"]]
    n = me["games"]
    p = me["winShare"]

    def describe(seat_id):
        params = seats[seat_id].get("params") or {}
        return {"seatId": seat_id, "strategy": seats[seat_id]["strategy"],
                "simulations": params.get("simulations"), "valueModel": params.get("valueModel"),
                "winShare": summary[seat_id]["winShare"], "avgScore": summary[seat_id]["avgScore"]}

    params = mine[0].get("params") or {}
    return {
        "result": result_path.replace(os.sep, "/"),
        "config": cfg.get("name"),
        "status": result["status"],
        "games": n,
        "seed": cfg["seed"],
        "seatOrder": cfg.get("seatOrder"),
        "simulations": params.get("simulations"),
        "leafRollout": params.get("leafRollout", 0),
        "winShare": p,
        "winShareCi95": 1.96 * (p * (1 - p) / n) ** 0.5 if n else None,
        "avgScore": me["avgScore"],
        "others": [describe(s["id"]) for s in cfg["seats"] if s["id"] != mine[0]["id"]],
    }


def add_match(model_path, result_path):
    """Records a match summary (the same result file replaces its earlier entry).

    Local models: in their own .meta.json. Official models (tracked by git): in ml/local/match-records/, so the tracked
    file stays untouched; read() merges both."""
    entry = match_entry(result_path, model_path)
    if is_official(model_path):
        records = [m for m in _local_records(model_path) if m["result"] != entry["result"]] + [entry]
        os.makedirs(local_records_dir(), exist_ok=True)
        with open(_records_path(model_path), "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        return entry
    meta = read(model_path, include_local=False)
    meta["matches"] = [m for m in meta.get("matches", []) if m["result"] != entry["result"]] + [entry]
    with open(model_path + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return entry


MODEL_FILES = ("", ".meta.json", ".check.txt")


def move_model(model_path, target_dir):
    """Moves a model with its .meta.json and .check.txt (promote to ml/models, or move to ml/local/models).
    Refuses when the target already has a model of that name. Returns the new path."""
    name = os.path.basename(model_path)
    target = os.path.join(target_dir, name)
    if os.path.exists(target):
        raise ValueError(f"{name} already exists in {os.path.relpath(target_dir, os.path.dirname(ML_DIR))}")
    os.makedirs(target_dir, exist_ok=True)
    local_matches = _local_records(model_path) if is_official(model_path) else []
    for suffix in MODEL_FILES:
        if os.path.exists(model_path + suffix):
            os.replace(model_path + suffix, target + suffix)
    if local_matches and not is_official(target):
        # leaving the official folder: the matches recorded beside it go back into its own metadata
        meta = read(target, include_local=False)
        known = {m["result"] for m in meta.get("matches", [])}
        meta["matches"] = meta.get("matches", []) + [m for m in local_matches if m["result"] not in known]
        with open(target + ".meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        os.remove(_records_path(model_path))
    return target
