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


def read(model_path):
    with open(model_path + ".meta.json", encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("format") != FORMAT or meta.get("formatVersion") != FORMAT_VERSION:
        raise ValueError(f"{model_path}.meta.json: unknown format")
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
    """Appends (or replaces, for the same result file) a match summary in <model>.meta.json."""
    meta = read(model_path)
    entry = match_entry(result_path, model_path)
    meta["matches"] = [m for m in meta.get("matches", []) if m["result"] != entry["result"]] + [entry]
    with open(model_path + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return entry
