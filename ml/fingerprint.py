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


def rules_name(revision, ruleset=None):
    """How a rules revision is shown to people: 'base-v1' (rule set 'base', revision 1; a variant would follow: base-v2-rich-start)."""
    return f"{ruleset or DEFAULT_RULESET}-v{revision}"


def load_versions(strategies=False):
    """The version control list docs/versions.json: ({track id: track dict}, error text or None).

    strategies=True: ((strategy track info, [one track per strategy]), error) instead."""
    import json
    path = os.path.join(ROOT, "docs", "versions.json")
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        if strategies:
            return (doc.get("strategyTrack", {}), doc.get("strategies", [])), None
        return {t["id"]: t for t in doc["tracks"]}, None
    except (OSError, ValueError, KeyError) as e:
        return ({}, []) if strategies else {}, f"讀不了 docs/versions.json：{e}"


def current_rules_revision():
    """RulesRevision of this checkout (Engine/Game/EngineInfo.cs)."""
    return _engine_constant("rules", ("Engine", "Game", "EngineInfo.cs"), "RulesRevision")


def current_feature_version():
    """The newest feature set of this checkout: FeatureSets.LatestVersion (Engine/Strategies/Mcts/FeatureSets.cs). Older versions
    (1 .. this) stay readable: models and data of an older version keep working, so a data run may ask for any of them."""
    return _engine_constant("features", ("Engine", "Strategies", "Mcts", "FeatureSets.cs"), r"public const int LatestVersion")


def feature_versions():
    """Every feature version the engine supports, oldest first."""
    return list(range(1, current_feature_version() + 1))


def current_format_version():
    """PositionDump.FormatVersion of this checkout (Engine/Simulation/PositionDump.cs)."""
    return _engine_constant("format", ("Engine", "Simulation", "PositionDump.cs"), r"public const int FormatVersion")


# ---------------------------------------------------------------- recipes

HASH_FORMAT = 2  # bump when the recipe's structure changes (every hash changes then; ask the user first)
DEFAULT_RULESET = "base"


def _load_json(path):
    import json
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


_tables = {}


def strategy_table(legacy=False):
    """Revision and resolved default parameters of every strategy per player count.

    Current: ml/strategy-params.json, written from the engine by PR_UPDATE_GOLDEN=1 dotnet test --filter Golden (a test keeps
    it equal to the code). Legacy: ml/strategy-params.legacy.json, frozen at strategies v1 / base-v1, for files written
    before the engine recorded resolvedSeats."""
    key = "legacy" if legacy else "current"
    if key not in _tables:
        name = "strategy-params.legacy.json" if legacy else "strategy-params.json"
        _tables[key] = _load_json(os.path.join(ML_DIR, name)).get("strategies", {})
    return _tables[key]


def current_strategy_revision(name):
    entry = strategy_table().get(str(name).lower())
    return entry["revision"] if entry else None


def resolve_seat(seat, players, legacy=False):
    """What StrategyRegistry.Resolve (C#) gives for a config seat: every parameter with the value used (defaults of this
    player count, config values win, unread config values kept) and the revisions of all strategy code involved."""
    table = strategy_table(legacy)
    name = str(seat.get("strategy", "")).lower()
    given = dict(seat.get("params") or {})
    if name == "rule-based":
        profile = str(given.get("profile", "corn-shipper")).lower()
        entry = table.get(profile, {})
        params = {**entry.get("params", {}).get(str(players), {}), "profile": profile, **given}
        revisions = {profile: entry.get("revision", 1)}
    elif name in table:
        entry = table[name]
        params = {**entry["params"].get(str(players), {}), **given}
        revisions = {name: entry["revision"]}
        if name == "mcts":  # the rollout strategy's code is part of the seat (resolved without parameters, as MCTS creates it)
            rollout = str(params.get("rolloutStrategy", "random"))
            revisions.update(resolve_seat({"strategy": rollout}, players, legacy)["revisions"])
    else:
        params, revisions = given, {}
    return {"strategy": name, "revisions": revisions, "params": params}


def _seat_recipe(resolved):
    params = {}
    for k, v in (resolved.get("params") or {}).items():
        params[k] = "model:" + model_digest(v) if k == "valueModel" and isinstance(v, str) and v else v
    return {"strategy": str(resolved["strategy"]).lower(), "revisions": dict(resolved.get("revisions") or {}), "params": params}


def sim_recipe(cfg, rules_revision=1, games=None, resolved_seats=None, legacy=True, ruleset=None):
    """The part shared by data and matches. cfg is a simulation config / result config / dump metadata (camelCase JSON).

    resolved_seats: the seats as the engine recorded them (resolvedSeats); without them the seats are resolved here, with
    the frozen legacy table (old files) or the current one (legacy=False: a run that has not happened yet)."""
    limits = {k: (cfg.get("limits") or {}).get(k, d) for k, d in DEFAULT_LIMITS.items()}
    options = {k: (cfg.get("options") or {}).get(k, d) for k, d in DEFAULT_OPTIONS.items()}
    seats = resolved_seats or [resolve_seat(s, cfg["players"], legacy) for s in cfg["seats"]]
    return {
        "hashFormat": HASH_FORMAT,
        "ruleset": ruleset or DEFAULT_RULESET,
        "rulesRevision": rules_revision or 1,
        "variant": "",          # rule variants (docs/TODO.md, ideas): reserved, so adding them later does not change old hashes
        "variantOptions": {},
        "players": cfg["players"],
        "games": cfg["games"] if games is None else games,
        "seed": cfg["seed"],
        "seatOrder": str(cfg.get("seatOrder", "random")).lower(),
        "seats": [_seat_recipe(s) for s in seats],
        "limits": limits,
        "options": options,
    }


def dump_recipe(meta):
    """Recipe of a position dump from its `<file>.bin.json` (works for dumps from before the hash existed)."""
    r = sim_recipe(meta, meta.get("rulesRevision", 1), games=meta["games"], resolved_seats=meta.get("resolvedSeats"),
                   ruleset=meta.get("rulesVersion"))
    return {**r, "kind": "dump", "rate": meta["rate"], "featureVersion": meta["featureVersion"], "formatVersion": meta["formatVersion"]}


def planned_dump_recipe(cfg, rate, feature_version=None):
    """Recipe of the dump a config would produce with this checkout's engine (cfg: games and seed already applied);
    feature_version: the feature set asked for (default: the newest)."""
    return {**sim_recipe(cfg, current_rules_revision(), legacy=False), "kind": "dump", "rate": rate,
            "featureVersion": feature_version or current_feature_version(), "formatVersion": current_format_version()}


def planned_match_recipe(cfg):
    return {**sim_recipe(cfg, current_rules_revision(), legacy=False), "kind": "match"}


def result_recipe(result):
    """Recipe of a Runner result file (a match)."""
    return {**sim_recipe(result["config"], result.get("rulesRevision", 1), resolved_seats=result.get("resolvedSeats"),
                         ruleset=result.get("rulesVersion")), "kind": "match"}


def strategy_name(name, revision):
    """How a strategy revision is shown: 'harbor-rush-v1'."""
    return f"{name}-v{revision}"


def stale_notes(recipe):
    """Why a data / match recipe no longer matches this checkout's engine: older rules or strategy revisions ([] = current)."""
    notes = []
    rev = recipe.get("rulesRevision", 1)
    if rev < current_rules_revision():
        notes.append(f"規則 {rules_name(rev, recipe.get('ruleset'))} → {rules_name(current_rules_revision(), recipe.get('ruleset'))}")
    seen = set()
    for seat in recipe.get("seats", []):
        for name, r in (seat.get("revisions") or {}).items():
            now = current_strategy_revision(name)
            if now is not None and r < now and name not in seen:
                seen.add(name)
                notes.append(f"{strategy_name(name, r)} → v{now}")
    return notes


def model_options(kind, options):
    """The training options that decide the model, in a fixed form (white lists above)."""
    keys = LGBM_OPTIONS if kind == "lightgbm" else MLP_OPTIONS
    out = {k: options[k] for k in keys if k in options}
    if "hidden" in out:
        out["hidden"] = [int(h) for h in str(out["hidden"]).replace("[", "").replace("]", "").split(",") if h.strip()]
    return out


def model_recipe(kind, feature_version, data_fingerprints, options):
    return {"hashFormat": HASH_FORMAT, "kind": kind, "featureVersion": feature_version, "data": sorted(data_fingerprints),
            "options": model_options(kind, options)}


def fingerprint(recipe):
    return digest(recipe)


# ---------------------------------------------------------------- differences

LABELS = {
    "players": "人數", "games": "局數", "seed": "種子", "rate": "抽樣率", "seatOrder": "座位順序",
    "rulesRevision": "規則版本", "featureVersion": "特徵版本", "formatVersion": "資料格式版本",
    "limits.maxRounds": "最大回合數", "limits.maxDecisionsPerGame": "每局最大決策數",
    "options.autoAdvanceForced": "自動跳過唯一合法動作", "kind": "種類", "data": "訓練資料",
    "hashFormat": "hash 格式版本", "ruleset": "規則集", "variant": "變體",
}
PARAM_LABELS = {"simulations": "模擬次數", "valueModel": "估值模型（檔案內容）", "leafRollout": "leafRollout"}


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
        if rest.startswith("revisions."):
            return f"座位 {n} 的策略版本 {rest[len('revisions.'):]}"
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
            out.append(f"規則版本：{rules_name(x or 1, old.get('ruleset'))} → {rules_name(y or 1, new.get('ruleset'))}")
        elif re.match(r"seats\[\d+\]\.revisions\.", path):
            out.append(f"{_label(path)}：{'v' + str(x) if x is not None else '（無）'} → {'v' + str(y) if y is not None else '（無）'}")
        elif path == "data":
            gone, added = sorted(set(x or []) - set(y or [])), sorted(set(y or []) - set(x or []))
            fmt = lambda fps: "、".join(names.get(f, short(f)) for f in fps)  # noqa: E731
            parts = ([f"新增 {fmt(added)}"] if added else []) + ([f"移除 {fmt(gone)}"] if gone else [])
            out.append("訓練資料：" + "；".join(parts))
        else:
            out.append(f"{_label(path)}：{_show(x)} → {_show(y)}")
    return out
