"""Recipe fingerprints: one hash that says whether two data files, models or matches were made from the same parameters.

A *recipe* is the set of parameters that decide the result; its *fingerprint* is the SHA-256 of the recipe in a fixed
form (keys sorted, 100 and 100.0 alike, text lower-cased where case carries no meaning). Same recipe -> same file
(the engine is deterministic in config and seed), so the fingerprint answers "is this the same thing?" and the recipes
themselves answer "what differs?" (`describe`).

What goes in (and what does not) is listed in ml/CLAUDE.md. In short:
  data (.bin)   players, games done, seed, rate, seat order, every seat's strategy and parameters (in order; a value
                model is its file CONTENT hash, not its name), limits, options, engine RulesRevision, dump format and
                feature version.  Not: thread count, file name, config name, seat ids.
  model         kind, feature version, the fingerprints of its data, the training options (white lists below).
                Not: model name, thread count, library versions (recorded, shown, not hashed).
  match         like data without rate / feature version, plus the engine RulesRevision.

RulesRevision is the integer in Engine/Game/EngineInfo.cs that is bumped by hand when the same config and seed would
give different results; files from before it existed count as revision 1.
"""
import hashlib
import os
import re

ML_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ML_DIR)

# defaults of the engine (SimulationConfig): older dumps do not record these, and configs may omit them
DEFAULT_LIMITS = {"maxRounds": 150, "maxDecisionsPerGame": 20000}
DEFAULT_OPTIONS = {"autoAdvanceForced": True}

# training options that decide the model; every other key of train_*.DEFAULTS must be listed in IGNORED_OPTIONS
# (tests/test_fingerprint.py fails when a new option is in neither list)
LGBM_OPTIONS = ("rounds", "leaves", "lr", "min_leaf", "feature_fraction", "bagging_fraction", "valid", "seed", "early_stopping")
MLP_OPTIONS = ("hidden", "epochs", "batch", "lr", "l2", "patience", "valid", "seed", "backend", "device")
IGNORED_OPTIONS = ("threads",)


# ---------------------------------------------------------------- hashing

def _norm(v):
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
        return int(v)
    return v


def canonical(obj):
    import json
    return json.dumps(_norm(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj):
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def short(fp):
    return (fp or "")[:8]


_file_cache = {}


def file_sha256(path):
    """SHA-256 of a file's content (models are a few MB); cached by path, size and modification time."""
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    if key not in _file_cache:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _file_cache[key] = h.hexdigest()
    return _file_cache[key]


def model_digest(value_model):
    """Content hash of the value model a config names (relative paths resolve from the project root, then by file name in
    ml/models and ml/local/models); 'missing:<name>' when the file is not there."""
    name = os.path.basename(str(value_model))
    for path in (value_model, os.path.join(ROOT, value_model), os.path.join(ML_DIR, "models", name),
                 os.path.join(ML_DIR, "local", "models", name)):
        if os.path.isfile(path):
            return file_sha256(path)
    return "missing:" + name


_constants = {}


def _engine_constant(key, path, name):
    """An integer constant of the C# engine, read from its source (the single place it is defined)."""
    if key not in _constants:
        try:
            with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
                _constants[key] = int(re.search(name + r"\s*=\s*(\d+)", f.read()).group(1))
        except (OSError, AttributeError, ValueError):
            _constants[key] = 1
    return _constants[key]


def current_engine_version():
    """EngineInfo.Version of this checkout (e.g. '0.2.0')."""
    if "engine" not in _constants:
        try:
            with open(os.path.join(ROOT, "Engine", "Game", "EngineInfo.cs"), encoding="utf-8") as f:
                _constants["engine"] = re.search(r'public const string Version\s*=\s*"([^"]+)"', f.read()).group(1)
        except (OSError, AttributeError):
            _constants["engine"] = "unknown"
    return _constants["engine"]


def rules_name(revision):
    """How a rules revision is shown to people: 'base-r1' (rule variant 'base', revision 1)."""
    return f"base-r{revision}"


def load_versions():
    """The version control list docs/versions.json: ({track id: track dict}, error text or None)."""
    import json
    path = os.path.join(ROOT, "docs", "versions.json")
    try:
        with open(path, encoding="utf-8") as f:
            return {t["id"]: t for t in json.load(f)["tracks"]}, None
    except (OSError, ValueError, KeyError) as e:
        return {}, f"讀不了 docs/versions.json：{e}"


def current_rules_revision():
    """RulesRevision of this checkout (Engine/Game/EngineInfo.cs)."""
    return _engine_constant("rules", ("Engine", "Game", "EngineInfo.cs"), "RulesRevision")


def current_feature_version():
    """ValueFeatures.Version of this checkout (Engine/Strategies/Mcts/ValueFeatures.cs)."""
    return _engine_constant("features", ("Engine", "Strategies", "Mcts", "ValueFeatures.cs"), r"public const int Version")


def current_format_version():
    """PositionDump.FormatVersion of this checkout (Engine/Simulation/PositionDump.cs)."""
    return _engine_constant("format", ("Engine", "Simulation", "PositionDump.cs"), r"public const int FormatVersion")


# ---------------------------------------------------------------- recipes

def _seat(seat):
    params = {}
    for k, v in (seat.get("params") or {}).items():
        params[k] = "model:" + model_digest(v) if k == "valueModel" and isinstance(v, str) else v
    return {"strategy": seat["strategy"], "params": params}


def sim_recipe(cfg, rules_revision=1, games=None):
    """The part shared by data and matches. cfg is a simulation config / result config / dump metadata (camelCase JSON)."""
    limits = {k: (cfg.get("limits") or {}).get(k, d) for k, d in DEFAULT_LIMITS.items()}
    options = {k: (cfg.get("options") or {}).get(k, d) for k, d in DEFAULT_OPTIONS.items()}
    return {
        "players": cfg["players"],
        "games": cfg["games"] if games is None else games,
        "seed": cfg["seed"],
        "seatOrder": str(cfg.get("seatOrder", "random")).lower(),
        "seats": [_seat(s) for s in cfg["seats"]],
        "limits": limits,
        "options": options,
        "rulesRevision": rules_revision or 1,
    }


def dump_recipe(meta):
    """Recipe of a position dump from its `<file>.bin.json` (works for dumps from before the fingerprint existed)."""
    r = sim_recipe(meta, meta.get("rulesRevision", 1), games=meta["games"])
    return {"kind": "dump", **r, "rate": meta["rate"], "featureVersion": meta["featureVersion"], "formatVersion": meta["formatVersion"]}


def planned_dump_recipe(cfg, rate):
    """Recipe of the dump a config would produce with this checkout's engine (cfg: games and seed already applied)."""
    return {"kind": "dump", **sim_recipe(cfg, current_rules_revision()), "rate": rate,
            "featureVersion": current_feature_version(), "formatVersion": current_format_version()}


def planned_match_recipe(cfg):
    return {"kind": "match", **sim_recipe(cfg, current_rules_revision())}


def result_recipe(result):
    """Recipe of a Runner result file (a match)."""
    return {"kind": "match", **sim_recipe(result["config"], result.get("rulesRevision", 1))}


def model_options(kind, options):
    """The training options that decide the model, in a fixed form (white lists above)."""
    keys = LGBM_OPTIONS if kind == "lightgbm" else MLP_OPTIONS
    out = {k: options[k] for k in keys if k in options}
    if "hidden" in out:
        out["hidden"] = [int(h) for h in str(out["hidden"]).replace("[", "").replace("]", "").split(",") if h.strip()]
    return out


def model_recipe(kind, feature_version, data_fingerprints, options):
    return {"kind": kind, "featureVersion": feature_version, "data": sorted(data_fingerprints),
            "options": model_options(kind, options)}


def fingerprint(recipe):
    return digest(recipe)


# ---------------------------------------------------------------- differences

LABELS = {
    "players": "人數", "games": "局數", "seed": "種子", "rate": "抽樣率", "seatOrder": "座位順序",
    "rulesRevision": "規則版本", "featureVersion": "特徵版本", "formatVersion": "資料格式版本",
    "limits.maxRounds": "最大回合數", "limits.maxDecisionsPerGame": "每局最大決策數",
    "options.autoAdvanceForced": "自動跳過唯一合法動作", "kind": "種類", "data": "訓練資料",
}
PARAM_LABELS = {"simulations": "模擬次數", "valueModel": "價值模型（檔案內容）", "leafRollout": "leafRollout"}


def _flatten(x, prefix=""):
    if isinstance(x, dict):
        for k in sorted(x):
            yield from _flatten(x[k], f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(x, list) and prefix != "data":
        for i, v in enumerate(x):
            yield from _flatten(v, f"{prefix}[{i}]")
    else:
        yield prefix, x


def _label(path):
    m = re.match(r"seats\[(\d+)\]\.(.*)", path)
    if m:
        n, rest = int(m.group(1)) + 1, m.group(2)
        if rest == "strategy":
            return f"座位 {n} 的策略"
        return f"座位 {n} 的" + PARAM_LABELS.get(rest.removeprefix("params."), rest.removeprefix("params."))
    if re.fullmatch(r"seats\[\d+\]", path):
        return f"座位 {int(path[6:-1]) + 1}"
    if path.startswith("options."):
        return LABELS.get(path, "參數 " + path[len("options."):])
    return LABELS.get(path, path)


def _show(v):
    if v is None:
        return "（無）"
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, str) and v.startswith("model:"):
        return "model " + v[6:14]
    if isinstance(v, list):
        return "、".join(str(x) for x in v)
    return str(v)


def describe(old, new, names=None):
    """Human-readable differences old -> new, e.g. ['局數：20,000 → 200,000', '抽樣率：0.01 → 0.001'].

    names maps a data fingerprint to a readable name (for the model recipe's 'data' list)."""
    names = names or {}
    a, b = dict(_flatten(old)), dict(_flatten(new))
    out = []
    for path in sorted(set(a) | set(b), key=lambda p: (0 if p == "kind" else 1, p)):
        x, y = a.get(path), b.get(path)
        if x == y:
            continue
        if path == "rulesRevision":
            out.append(f"規則版本：{rules_name(x or 1)} → {rules_name(y or 1)}")
        elif path == "data":
            gone, added = sorted(set(x or []) - set(y or [])), sorted(set(y or []) - set(x or []))
            fmt = lambda fps: "、".join(names.get(f, short(f)) for f in fps)  # noqa: E731
            parts = ([f"新增 {fmt(added)}"] if added else []) + ([f"移除 {fmt(gone)}"] if gone else [])
            out.append("訓練資料：" + "；".join(parts))
        else:
            out.append(f"{_label(path)}：{_show(x)} → {_show(y)}")
    return out
