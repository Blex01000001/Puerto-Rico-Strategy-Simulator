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
import re

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


def _parse_utc(text):
    """.NET writes 7 fractional digits ('2026-11-17T12:00:00.1234567Z'); datetime wants at most 6."""
    if not text:
        return None
    try:
        return datetime.datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", text).replace("Z", "+00:00"))
    except ValueError:
        return None


def result_seconds(result):
    """Wall-clock seconds of a Runner result (finished - started); None while running or when the file lacks the times."""
    a, b = _parse_utc(result.get("startedUtc")), _parse_utc(result.get("finishedUtc"))
    return round((b - a).total_seconds(), 1) if a and b else None


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
        "engineVersion": result.get("engineVersion"),
        "engineCommit": result.get("engineCommit"),
        "seconds": result_seconds(result),
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


def _duration(seconds):
    if seconds is None:
        return "—"
    s = int(round(seconds))
    return (f"{s // 3600} 小時 {s % 3600 // 60} 分" if s >= 3600 else f"{s // 60} 分 {s % 60} 秒" if s >= 60 else f"{s} 秒")


def _timing(entry):
    """(seconds, engine version, engine commit) of a match entry; older entries lack them, so the result file is read when it is still here."""
    got = (entry.get("seconds"), entry.get("engineVersion"), entry.get("engineCommit"))
    if all(v is not None for v in got):
        return got
    try:
        with open(os.path.join(os.path.dirname(ML_DIR), entry["result"]), encoding="utf-8") as f:
            result = json.load(f)
    except (OSError, ValueError, KeyError):
        return got
    return (got[0] if got[0] is not None else result_seconds(result),
            got[1] or result.get("engineVersion"), got[2] or result.get("engineCommit"))


def match_summary(entry, model_name, notes=""):
    """One match record as short Markdown to paste into a chat with an AI: what was played (config, seed, seat order, simulations),
    how long it took, the win shares with their 95% intervals, and the versions / hashes that say whether two results can be compared.
    No per-game data and no machine paths (the result path is relative to the project root)."""
    seconds, engine, commit = _timing(entry)
    games = entry.get("games") or 0
    rate = f"，{games / seconds:.2f} 局/秒" if seconds and games else ""
    rules = fingerprint.rules_name(entry.get("rulesRevision", 1), entry.get("ruleset"))

    def ci(p):
        return f"±{1.96 * (p * (1 - p) / games) ** 0.5:.1%}" if games and p is not None else "—"

    def pct(p):
        return f"{p:.1%}" if p is not None else "—"

    lines = [f"## 對戰結果：{entry.get('config') or entry['result']}（模型 {model_name}）", "",
             f"- 結果檔：`{entry['result']}`（{entry.get('status')}，{games:,} 局，種子 {entry.get('seed')}，座位順序 {entry.get('seatOrder')}）",
             f"- 耗時：{_duration(seconds)}{rate}",
             f"- 引擎 {engine or '—'}（commit {(commit or '—')[:7]}），規則 {rules}",
             "- 策略版本：" + ("、".join(fingerprint.strategy_name(k, v) for k, v in (entry.get("revisions") or {}).items()) or "—"),
             f"- 對戰 hash {fingerprint.short(entry.get('fingerprint')) or '—'}；模型檔 sha256 {(entry.get('modelSha256') or '—')[:8]}"]
    if notes:
        lines.append(f"- 備註：{notes}")
    lines += ["", "| 座位 | 策略 | 模擬次數 | 估值模型 | 勝率 | ±95% | 平均分 |", "|---|---|---|---|---|---|---|",
              f"| 本模型 | mcts | {entry.get('simulations')}（leafRollout {entry.get('leafRollout') or 0}） | {model_name} | "
              f"{pct(entry.get('winShare'))} | {ci(entry.get('winShare'))} | {entry.get('avgScore', 0):.1f} |"]
    for o in entry.get("others", []):
        sims = o.get("simulations")
        lines.append(f"| {o['seatId']} | {o['strategy']} | {sims if sims is not None else '—'} | "
                     f"{os.path.basename(o['valueModel']) if o.get('valueModel') else '—'} | "
                     f"{pct(o.get('winShare'))} | {ci(o.get('winShare'))} | {o.get('avgScore', 0):.1f} |")
    return "\n".join(lines)


def job_seconds(job):
    """Seconds between a background job's `started` and `finished` (ISO UTC strings); None while it has not finished."""
    a, b = _parse_utc(job.get("started")), _parse_utc(job.get("finished"))
    return (b - a).total_seconds() if a and b else None


def _seat_text(seat):
    p = seat.get("params") or {}
    extras = [f"{k} {p[k]}" for k in ("simulations", "leafRollout") if p.get(k) is not None]
    if p.get("valueModel"):
        extras.append("模型 " + os.path.basename(str(p["valueModel"]).replace("\\", "/")))
    return f"{seat['strategy']}（{'，'.join(extras)}）" if extras else seat["strategy"]


def dump_summary(dump_meta, path, title, seconds=None):
    """A finished (or cancelled) data job as short Markdown for an AI: the config as it played, the size, the sampling rate, the time
    and the versions / hash. dump_meta = the dump's .bin.json (positions.read_meta), path = the .bin file as shown (relative to the project root)."""
    d = data_summary([{**dump_meta, "path": path}])[0]
    games = d["games"]
    rate = f"，{games / seconds:.2f} 局/秒" if seconds and games else ""
    seats = "、".join(f"{s.get('id', i)}={_seat_text(s)}" for i, s in enumerate(dump_meta.get("seats", [])))
    return "\n".join([
        f"## 資料產生：{title}", "",
        f"- 輸出：`{d['path']}`（{d['status']}，{games:,} 局，{d['rows']:,} 列，抽樣率 {d['rate']:g}，種子 {d['seed']}，座位順序 {dump_meta.get('seatOrder')}）",
        f"- 耗時：{_duration(seconds)}{rate}",
        f"- {dump_meta.get('players')} 人局，規則 {fingerprint.rules_name(d['rulesRevision'], d['ruleset'])}，特徵版本 {dump_meta.get('featureVersion')}，"
        f"策略版本 " + ("、".join(fingerprint.strategy_name(k, v) for k, v in d["revisions"].items()) or "—"),
        f"- 座位：{seats or '—'}",
        f"- 資料 hash {fingerprint.short(d.get('fingerprint')) or '—'}"])


NOISY_PARAMS = {"verbose", "deterministic", "num_threads", "note", "objective", "loss", "bagging_freq"}


def train_summary(meta, name):
    """A trained model (its .meta.json) as short Markdown for an AI: what it was trained on, with which parameters, how long it took and
    the validation numbers. Win rates against MCTS (the real verdict) are in the match summaries, not here."""
    t, v = meta.get("training") or {}, meta.get("validation") or {}
    steps = ", ".join(f"{label} {t[k]}" for k, label in (("iterations", "輪數"), ("bestIteration", "最佳輪"), ("epochsRun", "epoch"), ("bestEpoch", "最佳 epoch")) if k in t)
    params = "、".join(f"{k} {', '.join(map(str, x)) if isinstance(x, list) else x}" for k, x in (meta.get("params") or {}).items() if k not in NOISY_PARAMS)
    lines = [f"## 模型訓練：{name}", "",
             f"- {meta.get('kind')}，{meta.get('players')} 人局，特徵版本 {meta.get('featureVersion')}（{meta.get('featureCount')} 個），"
             f"規則 {fingerprint.rules_name(meta.get('rulesRevision', 1))}，hash {fingerprint.short(meta.get('fingerprint')) or '—'}",
             f"- 耗時：{_duration(t.get('seconds'))}" + (f"（{steps}）" if steps else ""),
             f"- 訓練參數：{params or '—'}"]
    if v:
        stages = "、".join(f"回合 {b['rounds']} {b['mse']:.4f}" for b in v.get("byRound", []))
        lines += [f"- 驗證（{v.get('rows', 0):,} 列）：交叉熵 {v['crossEntropy']:.4f}，MSE {v['mse']:.4f}（常數基準 {v['constantMse']:.4f}），R² {v['r2']:.3f}",
                  f"- 各回合段 MSE：{stages or '—'}"]
    top = "、".join(f"{f['name']}" for f in (meta.get("topFeatures") or [])[:5])
    lines += [f"- 最重要的特徵（前 5）：{top or '—'}", "", "| 資料 | 局數 | 列數 | 抽樣率 | 種子 | 策略 | 估值模型 |", "|---|---|---|---|---|---|---|"]
    for d in meta.get("data", []):
        lines.append(f"| {d['path']} | {d['games']:,} | {d['rows']:,} | {d['rate']:g} | {d['seed']} | {'、'.join(d.get('strategies', []))} | "
                     f"{'、'.join(os.path.basename(x) for x in d.get('valueModels', [])) or '—'} |")
    lines += ["", "（驗證成績只是檢查訓練有沒有壞掉，判斷好壞要看對戰勝率。）"]
    return "\n".join(lines)


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


def _dump_file_name(entry_path):
    return os.path.basename(str(entry_path or "").replace("\\", "/"))


def _rename_dump_in_meta(meta, old_file, new_file):
    """Points the data entries of a model's metadata (data[].path and data[].source) at a renamed dump file.
    Returns whether anything changed. Display records only: no hash includes the file name."""
    changed = False
    for d in meta.get("data", []):
        if _dump_file_name(d.get("path")) == old_file:
            d["path"] = _renamed_path(d["path"], old_file, new_file)
            if d.get("source") == old_file:
                d["source"] = new_file
            changed = True
    return changed


def _model_metas(folder):
    for p in sorted(glob.glob(os.path.join(folder, "*.meta.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                yield p, json.load(f)
        except (OSError, json.JSONDecodeError):
            continue


def dump_references(dump_path):
    """Models whose metadata names this dump file, as {"local": [.meta.json paths on this machine, updated by rename_dump],
    "official": [tracked .meta.json paths, left alone]}."""
    old_file = os.path.basename(dump_path)
    out = {"local": [], "official": []}
    for key, folder in (("local", local_models_dir()), ("official", OFFICIAL_MODELS)):
        for p, meta in _model_metas(folder):
            if _rename_dump_in_meta(meta, old_file, old_file + "\0"):
                out[key].append(p)
    return out


def rename_dump(dump_path, new_name):
    """Renames a dump (`<name>.bin` and `<name>.bin.json`; the `.bin` extension stays). Points the metadata on this machine that names
    it (local models' data entries) at the new name; tracked official .meta.json files stay as git has them. Refuses invalid
    names and names already taken. Returns the new `.bin` path. The hash does not change (it never includes the file name)."""
    name = new_name.strip()
    if name.endswith(".bin"):
        name = name[:-4]
    if not name or any(c in name for c in INVALID_NAME_CHARS):
        raise ValueError("名稱不能空白，也不能有路徑符號或空白")
    target = os.path.join(os.path.dirname(dump_path), name + ".bin")
    if os.path.abspath(target) == os.path.abspath(dump_path):
        raise ValueError("名稱沒有改變")
    if os.path.exists(target) or os.path.exists(target + ".json"):
        raise ValueError(f"已經有叫 {name}.bin 的資料，換一個名稱")
    old_file, new_file = os.path.basename(dump_path), name + ".bin"
    refs = dump_references(dump_path)
    os.replace(dump_path, target)
    if os.path.exists(dump_path + ".json"):
        os.replace(dump_path + ".json", target + ".json")
        with open(target + ".json", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("name") in (old_file, old_file[:-4]):  # a name recorded inside follows the file
            meta["name"] = new_file if meta["name"] == old_file else name
            with open(target + ".json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
    for p in refs["local"]:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        _rename_dump_in_meta(data, old_file, new_file)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return target


# ---- compact text for an AI (the "copy for AI" buttons of the management pages): key=value lines, no paths, no prose

DIGEST_LIMIT = 30000  # characters; the UI shows the count and refuses to copy more


def _num(x, digits=4):
    return "—" if x is None else (f"{x:.{digits}f}" if isinstance(x, float) else str(x))


def _seat_digest(seat):
    p = seat.get("params") or {}
    extras = [f"{k}={p[k]}" for k in ("simulations", "leafRollout") if p.get(k) is not None]
    if p.get("valueModel"):
        extras.append("model=" + os.path.basename(str(p["valueModel"]).replace("\\", "/")))
    return f"{seat['strategy']}" + (f"({','.join(extras)})" if extras else "")


def dump_digest(name, dump_meta, hash_short, rules, used_by=(), size_mb=None, stale=()):
    """One dump as compact lines for an AI. dump_meta = its .bin.json; used_by = names of the models trained on it."""
    seats = " ".join(f"{i}={_seat_digest(s)}" for i, s in enumerate(dump_meta.get("seats", [])))
    lines = [f"D {name} players={dump_meta.get('players')} games={dump_meta.get('games')} rows={dump_meta.get('rows')} rate={dump_meta.get('rate')} "
             f"seed={dump_meta.get('seed')} order={dump_meta.get('seatOrder')} feat={dump_meta.get('featureVersion')} rules={rules} hash={hash_short or '—'} "
             f"status={dump_meta.get('status')} engine={dump_meta.get('engineVersion') or '—'}@{(dump_meta.get('engineCommit') or '—')[:7]}"
             + (f" sizeMB={size_mb}" if size_mb is not None else ""),
             f" seats: {seats or '—'}"]
    if used_by:
        lines.append(" usedBy: " + ",".join(used_by))
    if stale:
        lines.append(" older: " + "; ".join(stale))
    return "\n".join(lines)


def _loss_digest(meta):
    """' treesGrown=N trainCe=X gapCe=Y' for the first line of a model digest: the trees the training really grew (LightGBM; the saved model keeps
    `iterations` of them), and the training cross-entropy and the validation-minus-training gap at the saved model's round. Fields the metadata
    has no record of (older models, MLP) are left out. The curves themselves are never copied."""
    t = meta.get("training") or {}
    valid, train = t.get("validLossCurve") or [], t.get("trainLossCurve") or []
    out = []
    if meta.get("kind") == "lightgbm" and valid:
        out.append(f"treesGrown={len(valid)}")
    if valid and len(train) == len(valid):
        i = min(max((t.get("bestIteration") or len(valid)) - 1, 0), len(valid) - 1)
        out.append(f"trainCe={train[i]:.4f} gapCe={valid[i] - train[i]:+.4f}")
    return (" " + " ".join(out)) if out else ""


def model_digest(name, meta, stale=(), matches=True):
    """One model (its .meta.json) as compact lines for an AI: data, parameters, validation, matches (matches=False leaves the match records out).
    No loss curve, no paths."""
    t, v = meta.get("training") or {}, meta.get("validation") or {}
    params = " ".join(f"{k}={','.join(map(str, x)) if isinstance(x, list) else x}" for k, x in (meta.get("params") or {}).items() if k not in NOISY_PARAMS)
    lines = [f"M {name} kind={meta.get('kind')} players={meta.get('players')} feat={meta.get('featureVersion')}({meta.get('featureCount')}) "
             f"rules={fingerprint.rules_name(meta.get('rulesRevision', 1))} hash={fingerprint.short(meta.get('fingerprint')) or '—'} "
             f"trainSec={_num(t.get('seconds'), 0)} " + " ".join(f"{k}={t[k]}" for k in ("iterations", "bestIteration", "epochsRun", "bestEpoch") if k in t)
             + _loss_digest(meta),
             f" params: {params or '—'}"]
    if v:
        stages = ",".join(f"{b['rounds']}:{b['mse']:.4f}" for b in v.get("byRound", []))
        lines.append(f" valid: rows={v.get('rows')} ce={_num(v.get('crossEntropy'))} mse={_num(v.get('mse'))} baseMse={_num(v.get('constantMse'))} "
                     f"r2={_num(v.get('r2'), 3)} mseByRound={stages or '—'}")
    for d in meta.get("data", []):
        models = ",".join(os.path.basename(x) for x in d.get("valueModels", []))
        strategies = ",".join(dict.fromkeys(x for x in d.get("strategies", []) if x))
        lines.append(f" data: {_dump_file_name(d.get('path'))} games={d['games']} rows={d['rows']} rate={d['rate']:g} seed={d['seed']} "
                     f"rules={fingerprint.rules_name(d.get('rulesRevision', 1), d.get('ruleset'))} hash={fingerprint.short(d.get('fingerprint')) or '—'} "
                     f"seats={strategies}" + (f" selfplayModels={models}" if models else ""))
    top = ",".join(f["name"] for f in (meta.get("topFeatures") or [])[:10])
    if top:
        lines.append(f" topFeatures: {top}")
    for m in (meta.get("matches", []) if matches else []):
        games = m.get("games") or 0
        ws = m.get("winShare")
        ci = f"±{1.96 * (ws * (1 - ws) / games) ** 0.5:.3f}" if games and ws is not None else ""
        others = " ".join(f"{o['strategy']}{'(' + os.path.basename(o['valueModel']) + ')' if o.get('valueModel') else ''}"
                          f"={_num(o.get('winShare'), 3)}" for o in m.get("others", []))
        lines.append(f" match: {m.get('config') or '—'} games={games} seed={m.get('seed')} order={m.get('seatOrder')} sims={m.get('simulations')} "
                     f"leaf={m.get('leafRollout') or 0} win={_num(ws, 3)}{ci} avg={_num(m.get('avgScore'), 1)} vs {others or '—'}")
    if stale:
        lines.append(" older: " + "; ".join(stale))
    return "\n".join(lines)


def digest(items, legend=True):
    """Joins dump_digest / model_digest blocks (strings); the legend explains the format once."""
    head = ("# key=value lines. D=training data (dump), M=model. win/avg are shares/scores of the tested model seat; ±=95% half-width; "
            "ce=cross-entropy, mse by round range; rules=base-vN; hash=recipe hash (same hash = same recipe)\n") if legend else ""
    return head + "\n".join(items)


def _relpath(path, start):
    try:
        return os.path.relpath(path, start)
    except ValueError:  # another drive (Windows)
        return path


def move_model(model_path, target_dir):
    """Moves a model with its .meta.json and .check.txt (promote to ml/models, or move to ml/local/models).
    Refuses when the target already has a model of that name. Returns the new path."""
    name = os.path.basename(model_path)
    target = os.path.join(target_dir, name)
    if os.path.exists(target):
        raise ValueError(f"{name} already exists in {_relpath(target_dir, os.path.dirname(ML_DIR))}")
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
