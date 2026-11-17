"""`<model>.meta.json`: how a model was trained (parameters, data, validation) and, later, how it played.

Written next to every model by train_lgbm.py / train_mlp.py. The engine never reads it (models are checked by their
feature names); it is for people, the ML UI and later comparisons. Win rates from MCTS matches are the real verdict;
the validation numbers are only a sanity check.
"""
import datetime
import glob
import json
import os
import platform

import numpy as np

import fingerprint

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


def _revisions(recipe):
    """Strategy name -> revision over all seats of a data / match recipe."""
    out = {}
    for seat in recipe.get("seats", []):
        out.update(seat.get("revisions") or {})
    return dict(sorted(out.items()))


def data_summary(metas):
    """Per dump file: what it is and where it came from (its hash recipe gives the hash, rules and strategy revisions)."""
    recipes = [fingerprint.dump_recipe(m) for m in metas]
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
        "fingerprint": fingerprint.fingerprint(r),
        "ruleset": r["ruleset"],
        "rulesRevision": r["rulesRevision"],
        "revisions": _revisions(r),
    } for m, r in zip(metas, recipes)]


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


def write(model_path, kind, metas, params, training, validation, top_features, libraries, options):
    """options: the training options as the trainer received them (white-listed into the recipe, see fingerprint.py)."""
    data = data_summary(metas)
    recipe = fingerprint.model_recipe(kind, metas[0]["featureVersion"], [d["fingerprint"] for d in data], options)
    meta = {
        "format": FORMAT,
        "formatVersion": FORMAT_VERSION,
        "model": os.path.basename(model_path),
        "kind": kind,
        "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "players": metas[0]["players"],
        "featureVersion": metas[0]["featureVersion"],
        "featureCount": metas[0]["featureCount"],
        "data": data,
        "rulesRevision": max(d["rulesRevision"] for d in data),
        "recipe": recipe,
        "fingerprint": fingerprint.fingerprint(recipe),
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
        # same recipe -> same result; modelSha256 shows later whether the model file is still the one that played
        "fingerprint": fingerprint.fingerprint(fingerprint.result_recipe(result)),
        "ruleset": result.get("rulesVersion") or fingerprint.DEFAULT_RULESET,
        "rulesRevision": result.get("rulesRevision", 1),
        "revisions": _revisions(fingerprint.result_recipe(result)),
        "modelSha256": fingerprint.file_sha256(model_path),
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


INVALID_NAME_CHARS = '/\\:*?"<>| '


def _renamed_path(value, old_name, new_name):
    """value with its file name old_name replaced by new_name (folder and separators kept); None when it names another file."""
    if not isinstance(value, str) or not value or os.path.basename(value.replace("\\", "/")) != old_name:
        return None
    return value[:len(value) - len(old_name)] + new_name


def _rename_in_meta(meta, old_name, new_name):
    """Points the match opponents (others[].valueModel) and the self-play data (data[].valueModels) at the new name.
    Returns whether anything changed. Display records only: no hash includes the name."""
    changed = False
    for m in meta.get("matches", []):
        for o in m.get("others", []):
            new = _renamed_path(o.get("valueModel"), old_name, new_name)
            if new:
                o["valueModel"], changed = new, True
    for d in meta.get("data", []):
        models = d.get("valueModels") or []
        news = [_renamed_path(v, old_name, new_name) or v for v in models]
        if news != models:
            d["valueModels"], changed = sorted(news), True
    return changed


def _meta_files_naming(name):
    """Metadata written on this machine that names the model `name`: other local models' .meta.json and the match
    records of official models (ml/local/match-records). Tracked official .meta.json files are never edited."""
    out = []
    for p in sorted(glob.glob(os.path.join(local_models_dir(), "*.meta.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if _rename_in_meta(meta, name, name + "\0"):
            out.append((p, "meta"))
    for p in sorted(glob.glob(os.path.join(local_records_dir(), "*.matches.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                records = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if _rename_in_meta({"matches": records}, name, name + "\0"):
            out.append((p, "records"))
    return out


def model_references(model_path):
    """Files that name this model by its file name, as {"meta": [...], "official": [...], "configs": [...]}:
    meta = metadata on this machine (updated by rename_model), official = tracked official .meta.json (left alone),
    configs = data / match configs in ml/local (updated only when passed to rename_model)."""
    name = os.path.basename(model_path)
    official = []
    for p in sorted(glob.glob(os.path.join(OFFICIAL_MODELS, "*.meta.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                if _rename_in_meta(json.load(f), name, name + "\0"):
                    official.append(p)
        except (OSError, json.JSONDecodeError):
            continue
    configs = [p for p in local_config_files() if _config_names(p, name)]
    return {"meta": [p for p, _ in _meta_files_naming(name) if p != model_path + ".meta.json"],
            "official": official, "configs": configs}


def local_config_files():
    return sorted(glob.glob(os.path.join(LOCAL_DIR, "data-configs", "*.json")) + glob.glob(os.path.join(LOCAL_DIR, "matches", "*.json")))


def _config_names(path, name, new_name=None):
    """Whether a config's seats point at `name` (params.valueModel); with new_name, rewrites the file to the new name."""
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    found = False
    for seat in cfg.get("seats", []) if isinstance(cfg, dict) else []:
        params = seat.get("params") or {}
        new = _renamed_path(params.get("valueModel"), name, new_name or name)
        if new:
            found = True
            params["valueModel"] = new
    if found and new_name:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    return found


def rename_model(model_path, new_name, configs=()):
    """Renames a LOCAL model with its .meta.json and .check.txt (the extension stays; the name inside the metadata follows).
    Also points the metadata on this machine that names it (other local models' matches and data, official models'
    local match records) at the new name; tracked official .meta.json files stay as git has them. `configs`: config
    files in ml/local to update too (data or match configs whose seats use the model); others are refused.
    Refuses official models (they are in git), invalid names and names already used in ml/models or ml/local/models.
    Returns the new path. The hash does not change (it never includes the name)."""
    ext = os.path.splitext(model_path)[1]
    name = new_name.strip()
    if name.endswith(ext):
        name = name[:-len(ext)]
    if not name or any(c in name for c in INVALID_NAME_CHARS):
        raise ValueError("名稱不能空白，也不能有路徑符號或空白")
    if is_official(model_path):
        raise ValueError("正式模型在 git 裡，請先「移到本機」或在 git 裡改名")
    target = os.path.join(os.path.dirname(model_path), name + ext)
    if os.path.abspath(target) == os.path.abspath(model_path):
        raise ValueError("名稱沒有改變")
    if any(os.path.exists(os.path.join(d, name + ext)) for d in (OFFICIAL_MODELS, local_models_dir(), os.path.dirname(model_path))):
        raise ValueError(f"已經有叫 {name + ext} 的模型，換一個名稱")
    allowed = {os.path.abspath(p) for p in local_config_files()}
    if any(os.path.abspath(c) not in allowed for c in configs):
        raise ValueError("只能一起改 ml/local 裡的設定檔")
    old_name = os.path.basename(model_path)
    for suffix in MODEL_FILES:
        if os.path.exists(model_path + suffix):
            os.replace(model_path + suffix, target + suffix)
    if os.path.exists(target + ".meta.json"):
        with open(target + ".meta.json", encoding="utf-8") as f:
            meta = json.load(f)
        meta["model"] = os.path.basename(target)
        with open(target + ".meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    new_file = os.path.basename(target)
    for p, kind in _meta_files_naming(old_name):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        _rename_in_meta(data if kind == "meta" else {"matches": data}, old_name, new_file)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    for c in configs:
        _config_names(c, old_name, new_file)
    return target


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
