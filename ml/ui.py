"""ML UI: train value models and browse them (Streamlit).

    streamlit run ml/ui.py --server.address localhost      (or ml/start-ui.sh / ml\\start-ui.cmd)

Tabs: 訓練 (choose dumps and parameters, start a background job, live loss curve) and 模型詳細資料 / 模型清單 (every model in
ml/models with its .meta.json: parameters, data, validation, feature importance, match win rates; compare two).
Jobs run in their own process (jobs.py): closing this page or the UI does not stop them.
Reads the same folders as the Dashboard: results/ (PR_RESULTS_DIR overrides) and ml/models/.
"""
import datetime
import html
import glob
import json
import os
import re
import time

import streamlit as st

import check_env
import i18n
import pipeline_form

LANG_ENV = "PR_LANG"  # default language when neither the session nor ?lang= chose one (tests set zh-TW)


def lang():
    """Active language: the sidebar toggle (session), then ?lang= in the URL, then PR_LANG, then English."""
    for choice in (st.session_state.get("lang"), st.query_params.get("lang"), os.environ.get(LANG_ENV)):
        if choice in i18n.LANGS:
            return choice
    return i18n.DEFAULT


def t(key, **values):
    return i18n.translate(lang(), key, **values)


if check_env.missing_modules():
    # started with a Python that lacks the packages (e.g. pip installed them into another Python): say so plainly
    st.set_page_config(page_title="Puerto Rico Machine Learning", page_icon="🌱")
    st.error(t("missing.error", names=", ".join(check_env.missing_modules())))
    st.markdown(t("missing.python", python=check_env.sys.executable))
    st.markdown(t("missing.fix"))
    st.code(check_env.fix_command(), language=None)
    st.caption(t("missing.note"))
    st.stop()

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402

import fingerprint  # noqa: E402
import folders  # noqa: E402
import jobs  # noqa: E402
import modelmeta  # noqa: E402
import positions  # noqa: E402
import train_lgbm  # noqa: E402
import train_mlp  # noqa: E402

ROOT = jobs.ROOT
MODELS_DIR = os.path.join(ROOT, "ml", "models")                    # official models (tracked by git)
LOCAL_DIR = os.path.join(ROOT, "ml", "local")                      # this machine's workspace (ignored by git)
LOCAL_MODELS = os.path.join(LOCAL_DIR, "models")
LOCAL_CONFIGS = os.path.join(LOCAL_DIR, "data-configs")
LOCAL_MATCHES = os.path.join(LOCAL_DIR, "matches")
DASHBOARD_URL = "http://localhost:5080"

STATE_TEXT = {"waiting": "Queued", "queued": "Starting", "running": "Running", "done": "Done", "failed": "Failed", "cancelled": "Cancelled",
              "interrupted": t("job.state.interrupted"), "lost": t("job.state.lost")}
LOST_TEXT = t("job.lost_help")
KIND_TEXT = {"train_lgbm": "LightGBM", "train_mlp": "MLP", "lightgbm": "LightGBM", "mlp": "MLP", "dump": t("job.kind.dump"), "match": t("job.kind.match")}


def rel(path):
    """Path relative to the project root with forward slashes (what configs and meta files store)."""
    try:
        r = os.path.relpath(os.path.abspath(path), ROOT)
    except ValueError:  # other drive on Windows
        return path.replace(os.sep, "/")
    return path.replace(os.sep, "/") if r.startswith("..") else r.replace(os.sep, "/")


def absolute(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def folder_line(path, key):
    """A small grey line under a file list or picker: the path (relative to the project root) and a link-like 開啟資料夾 button."""
    with st.container(key=f"folderline-{key}"):
        c1, c2 = st.columns(2, vertical_alignment="center")
        c1.markdown(f"<span class='folder-path'>{plain(path)}</span>", unsafe_allow_html=True)
        if c2.button(t("common.open_folder"), key=f"openfolder-{key}"):
            ok, why = folders.open_folder(absolute(path), ROOT)
            if ok:
                st.toast(t("common.folder_opened"))
            else:
                st.toast(why, icon="⚠️")


# ---------------------------------------------------------------- data and models on disk

@st.cache_data(show_spinner=False)
def _dump_info(path, mtime):
    try:
        m = positions.read_meta(path)
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as e:
        return {"path": rel(path), "error": scrub(str(e))}
    meta = {k: v for k, v in m.items() if k != "featureNames"}
    def seat_text(s):  # an MCTS seat names the value model it plays with: mcts(4p-v2)
        vm = (s.get("params") or {}).get("valueModel")
        return f"{s.get('strategy')}({os.path.splitext(os.path.basename(str(vm)))[0]})" if vm and s.get("strategy") else s.get("strategy")
    strategies = [seat_text(s) for s in m.get("seats", [])]
    models = sorted({os.path.basename(str((s.get("params") or {}).get("valueModel"))) for s in m.get("seats", [])
                     if (s.get("params") or {}).get("valueModel")})
    return {"path": rel(path), "來源": m.get("name") or os.path.basename(path), "人數": m["players"],
            "局數": m["games"], "列數": m["rows"], "狀態": m["status"], "抽樣率": m["rate"],
            "特徵版本": m["featureVersion"], "大小 MB": round(os.path.getsize(path) / 1e6, 1),
            "策略": "、".join(dict.fromkeys(strategies)), "自我對戰模型": "、".join(models), "_features": m.get("featureCount"), "_meta": meta}


def scrub(message):
    """Never show the machine's full project path (same rule as the Dashboard)."""
    return message.replace(ROOT + os.sep, "").replace(ROOT, ".")


def list_dumps():
    """Readable dumps, plus 'writing' entries for dumps still being produced (no metadata yet, file growing)."""
    out = []
    for p in sorted(glob.glob(os.path.join(jobs.results_dir(), "ml", "*.bin"))):
        if not os.path.exists(p + ".json") and time.time() - os.path.getmtime(p) < 300:
            out.append({"path": rel(p), "writing": True, "大小 MB": round(os.path.getsize(p) / 1e6, 1)})
            continue
        info = dict(_dump_info(p, os.path.getmtime(p + ".json") if os.path.exists(p + ".json") else 0))
        if "_meta" in info:
            # outside the cache: a value model a self-play dump used may have been replaced since
            info["_recipe"] = fingerprint.dump_recipe(info["_meta"])
            info["_fp"] = fingerprint.fingerprint(info["_recipe"])
            info["_rules"] = (info["_recipe"]["ruleset"], info["_recipe"]["rulesRevision"])
            info["_stale"] = fingerprint.stale_notes(info["_recipe"], lang())
            info["hash"] = fingerprint.short(info["_fp"])
            info["規則版本"] = fingerprint.rules_name(info["_recipe"]["rulesRevision"], info["_recipe"]["ruleset"])
            info["版本狀態"] = version_text(info["_stale"])
            info["引擎 commit"] = info["_meta"].get("engineCommit", "—")
        out.append(info)
    return out


def version_text(notes):
    """'最新', or what is older than this checkout's engine ('舊：規則 base-v1 → base-v2；harbor-rush-v1 → v2')."""
    return t("ver.latest") if not notes else t("ver.old") + t("common.sep").join(notes)


def entry_stale(rules_revision, ruleset, revisions, strategies=()):
    """stale_notes for a recorded data / match entry (model metadata keeps no full recipe). Entries from before strategy
    revisions were recorded count as revision 1 of the strategies they name."""
    if not revisions:
        revisions = {str(n).lower(): 1 for n in strategies if n}
    return fingerprint.stale_notes({"rulesRevision": rules_revision or 1, "ruleset": ruleset, "seats": [{"revisions": revisions}]}, lang())


def model_stale(meta):
    """Everything about a model's data that is older than this checkout's engine."""
    notes = []
    for d in meta.get("data", []):
        for n in entry_stale(d.get("rulesRevision", 1), d.get("ruleset"), d.get("revisions"), d.get("strategies", [])):
            if n not in notes:
                notes.append(n)
    return notes


# internal (Chinese) keys of the dump rows -> i18n keys of the displayed column names
DUMP_COLUMNS = {"來源": "source", "人數": "players", "局數": "games", "列數": "rows", "狀態": "status", "抽樣率": "rate", "特徵版本": "feature",
                "大小 MB": "size", "策略": "strategies", "自我對戰模型": "selfplay", "規則版本": "rules", "版本狀態": "versions", "引擎 commit": "commit"}


HIDDEN_DUMP_COLUMNS = ("來源", "狀態", "自我對戰模型", "版本狀態")  # not shown in the data tables (the file name says the source)
CENTRED_DUMP_COLUMNS = ("人數", "特徵版本")


def table_view(rows, path_as=None):
    """Dump rows for display: no internal columns (those starting with _) and none of HIDDEN_DUMP_COLUMNS; the path column is
    dropped or renamed. Player count and feature version are text, so that column_config(df) can centre them."""
    df = pd.DataFrame(rows)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_") or c in HIDDEN_DUMP_COLUMNS])
    for c in CENTRED_DUMP_COLUMNS:
        if c in df:
            df[c] = [str(v) for v in df[c]]
    df = df.rename(columns={"path": path_as}) if path_as else df.drop(columns=["path"])
    return df.rename(columns={zh: t(f"dump.col.{key}") for zh, key in DUMP_COLUMNS.items()})


def dump_column_config():
    """Number formats and centring of the dump tables' columns (names are the translated ones)."""
    config = {t("dump.col.rows"): st.column_config.NumberColumn(format="localized"), t("dump.col.games"): st.column_config.NumberColumn(format="localized")}
    for key in ("players", "feature"):
        name = t(f"dump.col.{key}")
        config[name] = st.column_config.TextColumn(name, alignment="center")
    return config


def models_using(dump_rel):
    """Names of the models that were trained on this dump file (by the path recorded in their metadata)."""
    out = []
    for mp in model_files():
        meta = model_meta(mp)
        if meta and any(str(d.get("path", "")).replace("\\", "/") == dump_rel for d in meta.get("data", [])):
            out.append(os.path.basename(mp))
    return out


def job_reads(job):
    """Files a waiting / starting / running job will read (repo-relative, forward slashes): training data, the model a match
    plays, and the value models named in its config."""
    spec = job.get("spec", {})
    paths = list(spec.get("data") or [])
    if spec.get("model"):
        paths.append(spec["model"])
    if spec.get("config"):
        cfg = read_config(absolute(spec["config"]))
        for seat in (cfg or {}).get("seats", []):
            vm = (seat.get("params") or {}).get("valueModel")
            if vm:
                paths.append(vm)
    return {str(x).replace("\\", "/") for x in paths}


def pending_readers(out_rel):
    """Titles of the waiting / starting / running jobs that will read this file (overwriting it would change their input)."""
    want = out_rel.replace("\\", "/")
    return [job_title(j) for j in jobs.list_jobs() if j["state"] in ("waiting",) + jobs.BUSY and want in job_reads(j)]


def reader_problem(out_rel):
    titles = pending_readers(out_rel)
    return t("problem.reader", title=titles[0]) if titles else None


def same_name_notice(noun, exists, old, new, users=(), names=None):
    """Under a name field: what is already there under this name, and is it the same recipe?"""
    if not exists:
        return
    if old is None:
        st.warning(t("same.cannot_read", noun=noun))
    elif fingerprint.fingerprint(old) == fingerprint.fingerprint(new):
        st.info(t("same.identical", noun=noun, hash=fingerprint.short(fingerprint.fingerprint(new))))
    else:
        st.warning(t("same.differs", noun=noun, diff="\n".join(f"- {d}" for d in fingerprint.describe(old, new, names, lang()))))
    if users:
        st.warning(t("same.users", names=t("common.list").join(f"`{u}`" for u in users)))


def model_files():
    """Official models (ml/models) first, then local ones (ml/local/models)."""
    out = []
    for folder in (MODELS_DIR, LOCAL_MODELS):
        for p in sorted(glob.glob(os.path.join(folder, "*"))):
            if p.endswith((".meta.json", ".check.txt")) or not p.endswith((".txt", ".json")):
                continue
            out.append(p)
    return out


def place_of(path):
    return "official" if os.path.dirname(os.path.abspath(path)) == os.path.abspath(MODELS_DIR) else "local"


def model_path(name):
    """Full path of a model by file name (names are unique across ml/models and ml/local/models)."""
    return next((p for p in model_files() if os.path.basename(p) == name), os.path.join(MODELS_DIR, name))


def model_name_taken(name):
    return any(os.path.exists(os.path.join(d, name)) for d in (MODELS_DIR, LOCAL_MODELS))


@st.cache_data(show_spinner=False)
def _model_meta(path, mtime):
    try:
        return modelmeta.read(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def model_meta(path):
    mp = path + ".meta.json"
    rec = os.path.join(LOCAL_DIR, "match-records", os.path.basename(path) + ".matches.json")
    stamp = (os.path.getmtime(mp) if os.path.exists(mp) else 0, os.path.getmtime(rec) if os.path.exists(rec) else 0)
    return _model_meta(path, stamp)


def describe_match(m):
    """Short label: '300 sims vs Original MCTS 300 + cheap-engine + build-first'."""
    parts = []
    for o in m["others"]:
        if o["strategy"] == "mcts":
            parts.append(f"{t('match.orig_mcts')} {o.get('simulations') or ''}".strip() if not o.get("valueModel")
                         else t("match.mcts_with", model=os.path.basename(o["valueModel"])))
        else:
            parts.append(o["strategy"])
    leaf = t("match.leaf", n=m["leafRollout"]) if m.get("leafRollout") else ""
    return t("match.desc", sims=m.get("simulations"), leaf=leaf, opps="＋".join(parts) if lang() == "zh-TW" else " + ".join(parts))


def best_vs_default(meta):
    """Highest win share in a match against the original MCTS (the headline number of section 10)."""
    rows = [m for m in meta.get("matches", []) if any(o["strategy"] == "mcts" and not o.get("valueModel") for o in m["others"])]
    return max(rows, key=lambda m: m["winShare"]) if rows else None


# ---------------------------------------------------------------- 訓練

PARAM_DEFAULTS = {"rounds": "400", "leaves": "63", "lr": "0.05", "min_leaf": "200", "feature_fraction": "0.8", "bagging_fraction": "0.8", "early_stopping": "30", "threads": "0", "hidden": "256,128", "epochs": "12", "batch": "1024", "l2": "1e-5", "patience": "3", "backend": "auto", "device": "auto", "valid": "0.1", "seed": "1"}  # the default shown in the help text (labels: param.<name>)
PARAM_DOC_ROWS = {"train_lgbm": 8, "train_mlp": 8, "common": 2}  # rows per section of the parameter guide (texts: pdoc.<section>.<row>.<column>)


def param_doc(kind):
    """The parameter guide rows of a model kind plus the shared ones, in the active language."""
    rows = []
    for section in (kind, "common"):
        rows += [tuple(t(f"pdoc.{section}.{i}.{j}") for j in range(6)) for i in range(PARAM_DOC_ROWS[section])]
    return rows


def param_inputs(defaults, key, container_key="params"):
    """One input per parameter, typed after the default value. The grid gives every label the same height
    (CSS .st-key-params), so a title that wraps in a narrow window does not shift its row."""
    values = {}
    with st.container(key=container_key):  # (several sets on one page need keys of their own; the CSS matches "params" inside a key)
        cols = st.columns(3)
        for i, (name, default) in enumerate(defaults.items()):
            label = t(f"param.{name}") if name in PARAM_DEFAULTS else name
            title = f"{label}（{name}）" if lang() == "zh-TW" else f"{label} ({name})"
            tip = t("param.cli_tip", option=name.replace("_", "-"), default=default)
            with cols[i % 3]:
                k = f"{key}-{name}"
                if k not in st.session_state:  # a value put there by the program (a restored or loaded form) and `value=` together make Streamlit warn
                    st.session_state[k] = default if isinstance(default, (int, float)) and not isinstance(default, bool) else str(default)
                if isinstance(default, int) and not isinstance(default, bool):
                    values[name] = st.number_input(title, step=1, help=tip, key=k)
                elif isinstance(default, float):
                    values[name] = st.number_input(title, format="%g", help=tip, key=k)
                else:
                    values[name] = st.text_input(title, help=tip, key=k)
    return values


def grid(data, **kwargs):
    """st.dataframe with room for a horizontal scrollbar: Streamlit sizes a table to its rows exactly, so on Windows (a
    17 px scrollbar that takes space) the scrollbar of a wide table covered the last row. At most 10 rows are shown
    before the table scrolls vertically."""
    rows = len(getattr(data, "data", data))  # a pandas Styler keeps the frame in .data
    kwargs.setdefault("height", 35 * (min(rows, 10) + 1) + 2 + 18)
    return st.dataframe(data, **kwargs)


def busy_files(field):
    """Files that a waiting / starting / running job will read (they must not be deleted)."""
    used = set()
    for j in jobs.list_jobs():
        if j["state"] in ("waiting",) + jobs.BUSY:
            v = j.get("spec", {}).get(field)
            for f in (v if isinstance(v, list) else [v] if v else []):
                used.add(str(f).replace("\\", "/"))
    return used


def delete_gen():
    """Bumped after every deletion: tables with checkboxes put it in their key, so the old selection (row numbers that
    now point at other files) is dropped."""
    return st.session_state.get("del-gen", 0)


def delete_button(key, label, paths, extra_suffixes=(), busy=()):
    """A red delete button (right-aligned via the 'del-' key prefix) that asks for confirmation in a dialog; files a
    queued or running job needs are refused. A dialog closes with the rerun after deleting (a popover stayed open)."""
    with st.container(key=key):
        if st.button(label, key=f"{key}-open", disabled=not paths):
            confirm_delete(key, list(paths), tuple(extra_suffixes), tuple(busy))


@st.dialog(t("del.dlg"))
def confirm_delete(key, paths, extra_suffixes, busy):
    blocked = [p for p in paths if rel(p) in busy]
    if blocked:
        st.markdown(f'<span class="act-err">{t("del.blocked", files=t("common.list").join(plain(rel(p)) for p in blocked))}</span>',
                    unsafe_allow_html=True)
        if st.button(t("del.close"), key=f"keep-{key}-close"):
            st.rerun()
        return
    st.markdown(t("del.ask"))
    for p in paths:
        st.markdown(f"- `{rel(p)}`")
    c1, c2 = st.columns(2)
    if c1.button(t("queue.cancel"), key=f"keep-{key}-cancel", width="stretch"):
        st.rerun()
    if c2.button(t("del.ok"), key=f"{key}-confirm", width="stretch"):
        for p in paths:
            for f in [p] + [p + suf for suf in extra_suffixes]:
                if os.path.exists(f):
                    os.remove(f)
        st.session_state["del-gen"] = delete_gen() + 1
        st.cache_data.clear()
        st.rerun()


def training_tab():
    dumps = list_dumps()
    bad = [d for d in dumps if "error" in d]
    writing = [d for d in dumps if d.get("writing")]
    good = [d for d in dumps if "error" not in d and not d.get("writing")]
    with card("train-data", t("tr.card1")):
        if not good:
            for d in writing:
                st.info(t("tr.writing", path=d["path"], mb=d["大小 MB"]))
            st.info(t("tr.no_data", page=TAB_DATA))
            return
        players = sorted({d["人數"] for d in good})
        p = st.radio(t("tr.players"), players, index=len(players) - 1, horizontal=True, format_func=lambda n: t("match.players_n", n=n))
        rows = [d for d in good if d["人數"] == p]
        with st.container(key="filterbar-train"):  # quick filters (CSS .st-key-filterbar*); empty = all
            c1, c2, _ = st.columns([1, 1, 3])
            feature_opts = sorted({d["特徵版本"] for d in rows})
            rules_opts = sorted({d["規則版本"] for d in rows if "規則版本" in d})
            fv = c1.pills(t("dump.col.feature"), feature_opts, selection_mode="multi", key=f"tf-feature-{p}")
            rv = c2.pills(t("dump.col.rules"), rules_opts, selection_mode="multi", key=f"tf-rules-{p}")
        rows = [d for d in rows if d["特徵版本"] in (fv or feature_opts) and d.get("規則版本") in (rv or rules_opts)]
        if not rows:
            st.caption(t("mlist.none"))
            return
        df = table_view(rows)
        df = df.set_index(pd.Index([os.path.basename(r["path"]) for r in rows], name=t("dump.col.file")))
        # the filters are part of the key: a selection is by row number, which a different filter would point at other files
        picked = grid(df, on_select="rerun", selection_mode="multi-row", width="stretch",
                      key=f"dumps-{delete_gen()}-{'.'.join(map(str, fv or []))}-{'.'.join(rv or [])}", column_config=dump_column_config())
        chosen = [rows[i] for i in picked.selection.rows]
        folder_line(os.path.dirname(rows[0]["path"]) + "/", "train-data")
        for d in writing:
            st.info(t("tr.writing_wait", path=d["path"], mb=d["大小 MB"]))
        for d in bad:
            st.warning(t("tr.cannot_read", path=d["path"], error=d["error"]))
        versions = {d["特徵版本"] for d in chosen}
        total = sum(d["列數"] for d in chosen)
        if chosen:
            f = max(d.get("_features") or 430 for d in chosen)  # the feature count of the chosen version (430 for version 1, 512 for version 2)
            st.caption(t("tr.chosen", n=len(chosen), rows=f"{total:,}", f=f, lgbm=f"{total * f * 4 * 2.2 / 1e9:.1f}", mlp=f"{total * f * 2 * 1.5 / 1e9:.1f}"))
        else:
            st.caption(t("tr.pick_hint", page=TAB_DATA))

    with card("train-model", t("tr.card2")):
        kind = st.radio(t("tr.model"), ["train_lgbm", "train_mlp"], format_func=lambda k: KIND_TEXT[k], horizontal=True)
        defaults = dict(train_lgbm.DEFAULTS if kind == "train_lgbm" else train_mlp.DEFAULTS)
        options = param_inputs(defaults, kind)
        ext = ".txt" if kind == "train_lgbm" else ".json"
        # The default name has the time in it: it is made once per (players, kind) and kept in session_state under the widget's key. Passing it as
        # `value=` made a new widget every minute, which threw away the name the user had typed.
        if st.session_state.get("tr-name-for") != (p, kind):
            stamp = datetime.datetime.now().strftime("%m%d-%H%M")
            st.session_state["tr-name"] = f"{p}p-{'lgbm' if kind == 'train_lgbm' else 'mlp'}-{stamp}"
            st.session_state["tr-name-for"] = (p, kind)
        name = st.text_input(t("tr.name"), key="tr-name")
        name = name.strip()
        if name.endswith(ext):
            name = name[:-len(ext)]
        out = os.path.join(LOCAL_MODELS, name + ext)
        exists = os.path.exists(out)
        official_taken = os.path.exists(os.path.join(MODELS_DIR, name + ext))
        # recipe of this training run: the chosen data (by fingerprint) and the options that decide the model
        kind_name = "lightgbm" if kind == "train_lgbm" else "mlp"
        opts = {**defaults, **options}
        if kind_name == "mlp":
            backend, device = train_mlp.resolve_backend(opts)
            opts = {**opts, "backend": backend, "device": device}
        new_recipe = fingerprint.model_recipe(kind_name, chosen[0]["特徵版本"], [d["_fp"] for d in chosen], opts) if chosen else None
        if chosen:
            by_fp = {}
            for d in chosen:
                by_fp.setdefault(d["_fp"], []).append(d["來源"])
            for names_ in by_fp.values():
                if len(names_) > 1:
                    st.warning(t("tr.dup", names=t("common.list").join(f"`{n}`" for n in names_)))
            rules = {d["_rules"] for d in chosen}
            if len(rules) > 1:
                st.warning(t("tr.rules_mixed", names=t("common.list").join(fingerprint.rules_name(r, rs) for rs, r in sorted(rules))))
            stale = [(d["來源"], d["_stale"]) for d in chosen if d["_stale"]]
            if stale:
                st.warning(t("tr.stale", items="\n".join(f"- `{n}`: {t('common.sep').join(notes)}" if lang() != "zh-TW" else f"- `{n}`：{'；'.join(notes)}" for n, notes in stale)))
            fp_names = {d["_fp"]: d["來源"] for d in chosen}
            old_meta = model_meta(out) if exists else None
            old_recipe = (old_meta or {}).get("recipe")
            same_name_notice(t("noun.model"), exists, old_recipe, new_recipe, names=fp_names)
            twins = [os.path.basename(mp) for mp in model_files() if (model_meta(mp) or {}).get("fingerprint") == fingerprint.fingerprint(new_recipe)
                     and mp != out]
            if twins:
                st.info(t("tr.twins", list=t("common.list").join(f"`{name_}`" for name_ in twins)))
        overwrite = st.checkbox(t("tr.overwrite", name=name + ext), value=False) if exists else True

        problems = []
        if not chosen:
            problems.append(t("tr.p.no_data"))
        if len(versions) > 1:
            problems.append(t("tr.p.versions"))
        if not name or any(c in name for c in '/\\:*?"<>|'):
            problems.append(t("tr.p.name"))
        if exists and not overwrite:
            problems.append(t("tr.p.exists"))
        if official_taken:
            problems.append(t("tr.p.official", name=name + ext))
        if pending_output(rel(out)):
            problems.append(t("tr.p.pending", name=name + ext))
        if exists and reader_problem(rel(out)):
            problems.append(reader_problem(rel(out)))
        if action_row(t("tr.start"), "start-train", problems):
            spec = {"data": [d["path"] for d in chosen], "out": rel(out), "options": options}
            st.session_state["tr-name-for"] = None  # the next training gets a fresh default name (a new time stamp)
            start_job(kind, f"{KIND_TEXT[kind]} → {name + ext}", spec)

    with card("train-doc", t("tr.card_doc"), t("tr.doc_sub")):
        cols = [t(f"pdoc.col.{j}") for j in range(6)]
        st.table(pd.DataFrame(param_doc(kind), columns=cols).set_index(cols[0]))


# ---------------------------------------------------------------- jobs (shared by every tab)

TITLE = "Puerto Rico Machine Learning"
TAB_DATA, TAB_TRAIN, TAB_MATCH, TAB_MODELS, TAB_QUEUE, TAB_MODELLIST = (
    t(f"page.{p}") for p in ("data", "train", "match", "models", "queue", "modellist"))

# Same palette as the Dashboard (Dashboard/wwwroot/app.css); the base theme is in .streamlit/config.toml.
CSS = """
<style>
/* Streamlit's top toolbar is a 60px bar floating over the page (menu on the right, the re-open button of a collapsed sidebar on the
   left). The page title lives in that bar: it is the first thing in the content and exactly as tall as the bar, so nothing
   is lost under the toolbar and no extra padding is needed above it. The content's own left padding keeps it clear of the
   re-open button. If a Streamlit upgrade changes the bar height, change --bar-h to match. */
:root { --bar-h: 60px; }
.block-container { padding-top: 0 !important; padding-bottom: 2rem !important; }
[data-testid="stHeader"] { background: transparent !important; }
/* the <style> block itself sits in an (empty) element container: its 1rem row gap would push the title below the bar */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) { display: none !important; }
[data-testid="stHeading"], [data-testid="stHeading"] h1 { margin: 0 !important; padding: 0 !important; }
[data-testid="stHeading"] { height: var(--bar-h); display: flex; align-items: center; }
[data-testid="stHeading"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }  /* Streamlit gives headings -1rem here: it would shift the centring */
[data-testid="stHeading"] h1 { font-size: 1.5rem !important; line-height: 1.2 !important; }
/* the lines under the title (flow caption, page intro) sit one line apart: the title bar keeps its 60px for the toolbar, so pull the next
   element up into it, and shrink the 1rem row gap after top-level captions / paragraphs (the ones inside cards are not touched) */
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(> [data-testid="stHeading"]) { margin-bottom: -1.3rem; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(> [data-testid="stCaptionContainer"]),
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"]) { margin-bottom: -.55rem; }
/* narrow window: the sidebar starts collapsed and the content only has 1rem of left padding, so the re-open button would sit on the title */
@media (max-width: 768px) { [data-testid="stHeading"] { padding-left: 2.75rem !important; } }
/* the « button shares the brand row (🌱 Puerto Rico ...) instead of having a row of its own above it */
[data-testid="stSidebarHeader"] { position: absolute !important; top: .85rem; right: .7rem; width: auto !important; height: auto !important; min-height: 0 !important;
  padding: 0 !important; margin: 0 !important; z-index: 3; }
[data-testid="stSidebarHeader"] [data-testid="stLogoSpacer"] { display: none !important; }
[data-testid="stSidebarUserContent"] { padding-top: .7rem !important; }
/* cards: st.container(border=True, key="card-...") */
div[class*="st-key-card-"] { background: #1f2430; border: 1px solid #333a4b !important; border-radius: 6px; padding: .55rem 1rem .8rem 1rem; }
.card-head { display: flex; align-items: baseline; gap: .9rem; margin-bottom: .2rem; }
.card-head h3 { flex: none; }
.card-head .card-sub { flex: 1 1 0; min-width: 0; font-size: .82rem; line-height: 1.35; color: #8892a2; }  /* long text wraps beside the title, never under it */
div[class*="st-key-card-"] h3 { font-size: 1.05rem; margin: .1rem 0 .2rem 0; padding: 0; border-left: 3px solid #4aa8ff; padding-left: .55rem; }
/* inputs like the Dashboard: darker than the card behind them, with a border (the theme's input colour equals the card
   colour). Streamlit >= 1.6x renders inputs with react-aria (data-testid / react-aria-* classes), older versions with
   baseweb (data-baseweb): both are listed so the borders survive either version. */
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"],
.react-aria-ComboBox > div, [data-testid="stMultiSelect"] .react-aria-ComboBox > div,
div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div {
  background: #111418 !important; border: 1px solid #333a4b !important; border-radius: 4px !important; }
[data-testid="stTextInputRootElement"] input, [data-testid="stNumberInputContainer"] input, .react-aria-ComboBox input,
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea, textarea { background: transparent !important; }
[data-testid="stNumberInputContainer"] div[data-baseweb="input"], [data-testid="stNumberInputContainer"] [data-testid="stTextInputRootElement"] { border: 0 !important; }
[data-testid="stNumberInputContainer"] button { background: #1f2430 !important; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
.react-aria-ComboBox > div:focus-within, div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"] > div:focus-within { border-color: #4aa8ff !important; }
/* radio groups (人數, 模型, 對手…) get the same frame, sized to their options */
[data-testid="stRadioGroup"], div[role="radiogroup"] { display: inline-flex !important; width: auto !important; background: #111418;
  border: 1px solid #333a4b; border-radius: 4px; padding: .35rem .8rem; }
/* metrics (模型詳細資料: 種類, 資料列數, R², 最佳勝率) as framed tiles */
[data-testid="stMetric"] { background: #111418; border: 1px solid #333a4b; border-radius: 4px; padding: .45rem .8rem; }
[data-testid="stMetricValue"] > div { font-size: 1.7rem !important; }
/* delete buttons: red, at the right edge (delete_button wraps them in st.container(key="del-…")) */
div[class*="st-key-folderline-"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .5rem !important; align-items: center; }
div[class*="st-key-folderline-"] [data-testid="stColumn"] { flex: 0 1 auto !important; width: auto !important; min-width: 0 !important; }
div[class*="st-key-folderline-"] { margin: -.35rem 0 .35rem; }
.folder-path { font-size: .74rem; color: #8892a2; overflow-wrap: anywhere; }
div[class*="st-key-folderline-"] button { background: transparent !important; border: 0 !important; padding: 0 !important; min-height: 0 !important; height: auto !important; color: #4aa8ff !important; }
div[class*="st-key-folderline-"] button p { font-size: .74rem !important; text-decoration: underline; }
div[class*="st-key-del-"] { align-items: flex-end !important; }
div[class*="st-key-del-"] [data-testid="stPopover"] { width: auto !important; }
div[class*="st-key-del-"] button { background: #c43c3c !important; border: 0 !important; color: #fff !important; font-weight: 600 !important; }
div[class*="st-key-del-"] button:hover:not(:disabled) { filter: brightness(1.12); }
div[class*="st-key-stop-"] button { background: #c43c3c !important; border: 0 !important; color: #fff !important; font-weight: 600 !important; }
div[class*="st-key-stop-"] button:hover:not(:disabled) { filter: brightness(1.12); }
div[class*="st-key-stop-"] button:disabled { background: #4a2a2e !important; color: #b9a3a6 !important; }
.pl-detail { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: .6rem 1.1rem; padding: .45rem .3rem .55rem .75rem; }
.pl-detail .c { display: flex; flex-direction: column; min-width: 0; }
.pl-detail .k { color: #8892a2; font-size: .78rem; line-height: 1.3; }
.pl-detail .v { color: #eef1f5; font-size: .95rem; overflow-wrap: anywhere; }
.pl-rowtitle { font-size: 1.2rem; font-weight: 700; color: #eef1f5; padding-left: .55rem; border-left: 3px solid #4aa8ff; line-height: 1.3; }
div[class*="st-key-pl-seatcard"] { background: #1d2433; border: 1px solid #2b3447; border-radius: 4px; padding: .55rem .7rem; }
div[class*="st-key-pl-seatcard"] > div[data-testid="stVerticalBlock"], div[class*="st-key-pl-seatcard"] div[data-testid="stVerticalBlock"] { gap: .3rem; }
div[class*="st-key-pl-seatcard"] [data-testid="stWidgetLabel"] { min-height: 0; margin-bottom: .1rem; }
div[class*="st-key-pl-seatcard"] [data-testid="stWidgetLabel"] p { font-size: .8rem; font-weight: 600; color: #aab3c5; line-height: 1.2; }
div[class*="st-key-pl-seatcard"] [data-testid="stTextInputRootElement"], div[class*="st-key-pl-seatcard"] div[data-baseweb="select"] > div,
div[class*="st-key-pl-seatcard"] .react-aria-ComboBox { height: 2rem; min-height: 2rem; }
div[class*="st-key-pl-seatcard"] input { padding: .2rem .5rem; height: 100%; min-height: 0; font-size: .9rem; }
div[class*="st-key-pl-seatcard"] div[data-baseweb="select"] > div { padding-top: 0; padding-bottom: 0; }
div[class*="st-key-pl-addbox"] { border: 2px dashed #3a4258; border-radius: 8px; padding: .7rem .8rem; margin-top: .2rem; }
div[class*="st-key-del-"] button:disabled { background: #4a2a2e !important; color: #b9a3a6 !important; }
/* buttons like the Dashboard: blue when they can start, locked otherwise */
button[kind="primary"] { background: #4aa8ff !important; border: 0 !important; color: #07131f !important; font-weight: 600 !important; }
button[kind="primary"]:hover:not(:disabled) { filter: brightness(1.12); }
button[kind="primary"]:disabled { background: #2a3040 !important; color: #8892a2 !important; cursor: not-allowed !important; }
[data-testid="stPopover"] button, button[kind="primary"], button[kind="secondary"] { white-space: nowrap; }
.act-note { color: #8892a2; font-size: .82rem; line-height: 1.35; }
.act-err { color: #ec6a6a; font-size: .82rem; line-height: 1.35; }
.pl-problems { min-height: 2.4rem; font-size: .82rem; line-height: 1.35; margin: -.5rem 0 -.3rem; }
/* parameter grid: every label gets the height of two lines, so wrapped and unwrapped titles line up */
[class*="st-key-params"] [data-testid="stWidgetLabel"] { min-height: 2.6rem; display: flex; align-items: flex-end; }
/* sidebar: long job titles stay on one line and fade out */
.side-title { white-space: nowrap; overflow: hidden; color: #b4bcc9; font-size: .85rem;
  -webkit-mask-image: linear-gradient(to right, #000 78%, transparent); mask-image: linear-gradient(to right, #000 78%, transparent); }
.side-state { font-size: .85rem; }
.side-note { color: #8892a2; font-size: .78rem; margin: .1rem 0; }
/* version page: tiles and tables like the Dashboard's 版本控管 page (same look in both UIs) */
.vtiles { display: flex; flex-wrap: wrap; gap: .75rem; margin: .2rem 0 .6rem; }
/* the label takes its own line at the top (a long one wraps and pushes the value down), the value is centred in the rest */
.vtile { position: relative; flex: 1 1 9rem; min-height: 5.6rem; display: flex; flex-direction: column;
  padding: .35rem .55rem .55rem; background: #111418; border: 1px solid #333a4b; border-radius: 4px; }
.vtile .l { color: #8892a2; font-size: 15px; line-height: 1.25; text-align: left; padding-right: 1.3rem; }
.vtile .v { flex: 1; display: flex; align-items: center; justify-content: center; text-align: center;
  font-size: 1.55rem; font-weight: 600; color: #eef1f5; line-height: 1.2; font-variant-numeric: tabular-nums; }
/* the model details page: the value sits in the middle of the whole tile (the label stays at the top, the tile is a bit taller so a two-line label clears it) */
.vtiles.mid .vtile { min-height: 6.8rem; }
.vtiles.mid .vtile .v { position: absolute; inset: 0; pointer-events: none; }
.vtiles.mid .vtile .q { z-index: 2; }
.vnote { color: #b4bcc9; font-size: .85rem; line-height: 1.5; margin: .1rem 0 .35rem; }
table.vtable { border-collapse: collapse; width: 100%; font-size: .85rem; margin-top: .4rem; font-variant-numeric: tabular-nums; }
table.vtable th { color: #8892a2; font-weight: 600; font-size: .78rem; letter-spacing: .04em; background: #171a21; text-align: center; white-space: nowrap;
  padding: .35rem .55rem; border-bottom: 1px solid #333a4b; }
table.vtable th, table.vtable td { border-top: 0 !important; border-left: 0 !important; border-right: 0 !important; }
table.vtable td { padding: .35rem .55rem; border-bottom: 1px solid #333a4b; vertical-align: middle; }
table.vtable td.c { text-align: center; white-space: nowrap; }
table.vtable td.l { text-align: left; }
table.vtable td.nw { white-space: nowrap; }
table.vtable td ul { margin: 0; padding-left: 1.1rem; }
table.vtable td li { margin: 0; }
table.vtable tbody tr:hover td { background: #1f2430; }
.vtile .q { position: absolute; top: .3rem; right: .45rem; width: 1rem; height: 1rem; border: 1px solid #8892a2; border-radius: 50%;
  color: #8892a2; font-size: .68rem; line-height: .95rem; text-align: center; cursor: help; }
/* the model picker of the details page: a bigger label and dropdown */
div[class*="st-key-modelpick"] [data-testid="stWidgetLabel"] p { font-size: 1.15rem; font-weight: 700; }
div[class*="st-key-modelpick"] [data-testid="stSelectbox"] { font-size: 1.15rem; }
div[class*="st-key-modelpick"] .react-aria-ComboBox > div, div[class*="st-key-modelpick"] div[data-baseweb="select"] > div { min-height: 3.1rem; }
div[class*="st-key-modelpick"] [data-testid="stSelectbox"] input, div[class*="st-key-modelpick"] [data-testid="stSelectbox"] div { font-size: 1.15rem; }
/* quick filters (model list): one flat bar, a small label and round chips per group; a chosen chip is filled blue */
div[class*="st-key-filterbar"] { background: #171a21; border: 1px solid #2a3040; border-radius: 6px; padding: .35rem .8rem .5rem; margin-bottom: .3rem; }
div[class*="st-key-filterbar"] [data-testid="stHorizontalBlock"] { gap: 1.6rem !important; flex-wrap: wrap; }
div[class*="st-key-filterbar"] [data-testid="stColumn"] { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
div[class*="st-key-filterbar"] [data-testid="stWidgetLabel"] p { font-size: .72rem; font-weight: 700; letter-spacing: .12em; color: #8892a2; margin: 0 0 .2rem; }
div[class*="st-key-filterbar"] button[data-variant="pills"] { background: transparent; border: 1px solid #3a4258; border-radius: 999px; color: #b4bcc9;
  padding: .1rem .75rem; min-height: 0; font-size: .85rem; }
div[class*="st-key-filterbar"] button[data-variant="pills"]:hover { border-color: #4aa8ff; color: #eef1f5; }
div[class*="st-key-filterbar"] button[data-variant="pills"][aria-pressed="true"] { background: #1d3a5c; border-color: #4aa8ff; color: #fff; font-weight: 600; }
table.vtable.doc th { text-align: left; } table.vtable.doc td { vertical-align: top; }
table.vtable.cmp { table-layout: fixed; }  /* compare: equal model columns, long data lists wrap */
table.vtable.cmp th:first-child { width: 12rem; } table.vtable.cmp th:last-child { width: 3.5rem; }
table.vtable.cmp td { overflow-wrap: anywhere; }
table.vtable td.best { color: #4aa8ff; font-weight: 700; background: rgba(74, 168, 255, .13); }
/* left navigation (Dashboard style): brand, section headings, one full-width entry per page, the active one highlighted */
section[data-testid="stSidebar"] { background: #171a21 !important; border-right: 1px solid #000; }
/* a narrower navigation (Streamlit's default is 300px); the brand keeps its own width on two lines, long entries are not wrapped. Only while
   it is open: a collapsed sidebar is moved away by Streamlit with its own width */
section[data-testid="stSidebar"]:not([aria-expanded="false"]) { width: 14rem !important; min-width: 14rem !important; max-width: 14rem !important; }
.nav-brand { white-space: nowrap; }
.nav-brand { display: flex; align-items: center; gap: .55rem; font-weight: 700; color: #fff; line-height: 1.25; font-size: .95rem;
  padding: .2rem 0 .7rem; border-bottom: 1px solid #333a4b; margin-bottom: .2rem; }
.nav-brand .nav-icon { font-size: 1.5rem; }
.navsec { font-size: .68rem; font-weight: 700; letter-spacing: .14em; color: #8892a2; padding: .6rem .2rem .15rem; line-height: 1.2; }
div[class*="st-key-nav-"] button, div[class*="st-key-navon-"] button { justify-content: flex-start !important; background: transparent !important;
  border: 0 !important; color: #b4bcc9 !important; font-weight: 500 !important; padding: .45rem .7rem !important; min-height: 0 !important; }
div[class*="st-key-nav-"] button:hover { color: #eef1f5 !important; background: #1f2430 !important; }
div[class*="st-key-navon-"] button { color: #fff !important; background: #1d3a5c !important; box-shadow: inset 3px 0 0 #4aa8ff; }
div[class*="st-key-nav-"] button > div, div[class*="st-key-navon-"] button > div { justify-content: flex-start !important; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .3rem; }
section[data-testid="stSidebar"] [data-testid="stMarkdown"], section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
/* the current job sits at the bottom of the navigation */
[data-testid="stSidebarUserContent"] { min-height: calc(100vh - 2.5rem); display: flex; flex-direction: column; padding-bottom: 1rem !important; }
[data-testid="stSidebarUserContent"] > div:first-child { flex: 1; display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] > div:first-child > [data-testid="stVerticalBlock"] { flex: 1; }
[data-testid="stLayoutWrapper"]:has(> .st-key-side-status), .st-key-side-status { margin-top: auto !important; }
.st-key-side-status { border-top: 1px solid #333a4b; padding-top: .2rem; }
/* job list: one framed row per job, the left edge coloured by state */
div[class*="st-key-qrow-"] { background: #111418; border: 1px solid #333a4b; border-radius: 6px; padding: .45rem .8rem; }
div[class*="st-key-qrow-running"], div[class*="st-key-qrow-queued"] { border-left: 4px solid #4aa8ff; }
div[class*="st-key-qrow-waiting"] { border-left: 4px solid #e0a410; }
div[class*="st-key-qrow-done"] { border-left: 4px solid #3fa83f; }
div[class*="st-key-qrow-failed"], div[class*="st-key-qrow-interrupted"] { border-left: 4px solid #ec6a6a; }
div[class*="st-key-qrow-cancelled"] { border-left: 4px solid #8892a2; }
div[class*="st-key-qrow-lost"] { border-left: 4px solid #e8672f; }
.side-state.lost { color: #e8672f; font-size: .8rem; }
.st-key-qhead { padding: 0 .8rem 0 calc(.8rem + 4px); color: #b4bcc9; }
.side-state.failed, .side-state.interrupted { color: #ec6a6a; } .side-state.done { color: #3fa83f; } .side-state.cancelled { color: #8892a2; }
</style>
"""


def plain(text):
    """Problem texts may contain `code` marks; the inline hints are plain HTML."""
    import html
    return html.escape(str(text).replace("`", ""))


def action_row(label, key, problems, extra=None):
    """A start button with its hint on the same line, to its right: blue when it can start, locked with the reasons in
    red otherwise; while jobs run, the hint says where the new one will queue. Returns True when clicked."""
    c1, c2 = st.columns([2.2, 5], vertical_alignment="center")
    with c1:
        clicked = st.button(start_label(label), type="primary", disabled=bool(problems), key=key, width="stretch")
    with c2:
        if problems:
            st.markdown(f'<span class="act-err">{t("act.cannot", reasons=t("common.sep").join(plain(p) for p in problems))}</span>', unsafe_allow_html=True)
        else:
            notes = [extra] if extra else []
            active, waiting = jobs.active_job(), jobs.waiting_jobs()
            if active or waiting:
                notes.append(t("act.queue_note", pos=len(waiting) + 1, ahead=(1 if active else 0) + len(waiting)))
            if notes:
                st.markdown(f'<span class="act-note">{"。".join(plain(n) for n in notes)}</span>', unsafe_allow_html=True)
    return clicked


def card(key, title=None, sub=None):
    """A bordered card like the Dashboard's panels. `sub` (plain text) is the short explanation: it starts on the same line as the
    title; when it is too long for the card it wraps inside its own column beside the title."""
    c = st.container(border=True, key=f"card-{key}")
    if title and sub:
        c.markdown(f"<div class='card-head'><h3>{html.escape(title)}</h3><span class='card-sub'>{html.escape(sub)}</span></div>", unsafe_allow_html=True)
    elif title:
        c.markdown(f"### {title}")
    return c


def job_title(job):
    """A job's title in the active language (jobs made with a title key), else the text stored with it."""
    if job.get("titleKey"):
        try:
            return t(job["titleKey"], **(job.get("titleArgs") or {}))
        except (KeyError, IndexError, ValueError):
            pass
    return job["title"]


def start_job(kind, title, spec, title_key=None, **title_args):
    try:
        job_id = jobs.start(kind, title, spec, title_key, title_args)
        st.session_state["job-select"] = job_id  # the 工作 tab follows the new job
        pos = jobs.queue_position(job_id)
        st.session_state["job-started"] = t("job.started_queued", pos=pos) if pos else t("job.started_now", page=TAB_QUEUE)
        st.rerun()
    except (RuntimeError, ValueError, TimeoutError) as e:
        st.error(str(e))


def start_label(text):
    """The start buttons say 加入排隊 while another job runs: the new one waits for its turn."""
    return t("btn.queue") if jobs.active_job() or jobs.waiting_jobs() else text


def pending_output(out_rel):
    """True when a waiting / starting / running job will write this output (two jobs must not write the same file)."""
    want = out_rel.replace("\\", "/")
    return any(str(j.get("spec", {}).get("out", "")).replace("\\", "/") == want
               for j in jobs.list_jobs() if j["state"] in ("waiting",) + jobs.BUSY)


def progress_of(job, evs):
    """(fraction, text) for any job kind, or None while nothing is known yet."""
    steps = [e for e in evs if e["stage"] in ("iteration", "epoch", "games")]
    if not steps:
        if any(e["stage"] == "publish" for e in evs):
            return None, t("progress.publish")
        return None, t("progress.reading") if job["kind"].startswith("train") else t("progress.starting")
    last = steps[-1]
    if last["stage"] == "games":
        n, total = last["done"], last["total"]
        return n / max(1, total), t("progress.games", n=f"{n:,}", total=f"{total:,}")
    n = last.get("iteration") or last.get("epoch")
    total = last.get("total") or n
    return min(1.0, n / max(1, total)), t("progress.trees" if last["stage"] == "iteration" else "progress.epochs", n=n, total=total)


def watch_states(all_jobs):
    """Fragments refresh alone; when any job changes state, rerun the whole page (start buttons, lists).

    Also the queue's safety net: a job that died without handing over (machine asleep, killed) leaves waiting jobs
    behind; start the next one."""
    if not any(j["state"] in jobs.BUSY for j in all_jobs) and any(j["state"] == "waiting" for j in all_jobs):
        try:
            jobs.start_next()
        except TimeoutError:
            pass
    signature = tuple((j["id"], j["state"]) for j in all_jobs)
    if st.session_state.get("job-signature") not in (None, signature):
        st.session_state["job-signature"] = signature
        st.rerun(scope="app")
    st.session_state["job-signature"] = signature


@st.fragment(run_every=2)
def sidebar_status():
    import html
    all_jobs = jobs.list_jobs()
    watch_states(all_jobs)
    active, waiting = jobs.active_job(), jobs.waiting_jobs()
    st.markdown(f'<div class="navsec">{t("side.current")}</div>', unsafe_allow_html=True)
    if active:
        st.markdown(f'<div class="side-title" title="{html.escape(job_title(active))}">{html.escape(job_title(active))}</div>',
                    unsafe_allow_html=True)
        frac, text = progress_of(active, jobs.events(active["id"]))
        lost = active["state"] == "lost"
        c1, c2 = st.columns([3, 1.3], vertical_alignment="bottom")
        if lost:
            c1.markdown(f'<div class="side-state lost">{t("side.lost")}</div>', unsafe_allow_html=True)
        else:
            c1.progress(frac or 0.0, text=text)
        if c2.button(t("side.end") if lost else t("side.cancel"), key=f"stop-side-{active['id']}", width="stretch",  # stop-: red (CSS)
                     help=LOST_TEXT if lost else None):
            jobs.cancel(active["id"])
    else:
        st.markdown(f'<div class="side-note">{t("side.idle")}</div>', unsafe_allow_html=True)
    if waiting:
        st.markdown(f'<div class="side-note">{t("side.queued", n=len(waiting))}</div>', unsafe_allow_html=True)


QUEUE_STATE = {"running": ("Running", "#4aa8ff"), "queued": ("Starting", "#4aa8ff"), "waiting": ("Queued", "#e0a410"),
               "done": ("Done", "#3fa83f"), "failed": ("Failed", "#ec6a6a"), "cancelled": ("Cancelled", "#8892a2"),
               "interrupted": ("Interrupted", "#ec6a6a"), "lost": ("Lost", "#e8672f")}


def _epoch(text):
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def _duration(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s_ = divmod(rem, 60)
    return f"{h}:{m:02d}:{s_:02d}" if h else f"{m}:{s_:02d}"


def elapsed_text(job):
    started, finished = _epoch(job.get("started")), _epoch(job.get("finished"))
    if job["state"] == "waiting":
        return t("elapsed.waited", time=_duration(time.time() - job.get("createdEpoch", time.time())))
    if started is None:
        return "—"
    return _duration((finished or time.time()) - started)


def remark(job, col):
    """備註 column: errors collapsed, otherwise a one-line result."""
    state, result = job["state"], job.get("result") or {}
    if state == "failed":
        with col.expander(t("remark.error"), expanded=False):
            st.markdown(f'<span class="act-err" style="overflow-wrap:anywhere">{plain(scrub(job.get("error", "")))[:600]}</span>', unsafe_allow_html=True)
            st.caption(t("remark.full_log"))
    elif state == "interrupted":
        col.caption(t("remark.interrupted"))
    elif state == "lost":
        col.markdown(f'<span class="act-note" style="color:#e8672f">{t("remark.lost")}</span>',
                     unsafe_allow_html=True)
    elif state == "cancelled" and result.get("stoppedBy"):
        col.caption(t("remark.pipeline_stopped"))
    elif state == "cancelled" and result.get("summary"):
        col.caption(scrub(result["summary"])[:120])
    elif state == "done" and job["kind"] == "match" and result.get("match"):
        m = result["match"]
        col.caption(t("remark.match", win=f"{m['winShare']:.1%}", ci=f"{m['winShareCi95']:.1%}", games=m["games"]))
    elif state == "done" and job["kind"].startswith("train") and result.get("validation"):
        col.caption(f"R² {result['validation']['r2']:.3f} → {rel(result['model'])}")
    elif state == "done" and job["kind"] == "dump" and result.get("rows"):
        col.caption(t("remark.dump", games=f"{result['games']:,}", rows=f"{result['rows']:,}"))
    elif state == "waiting":
        col.caption(t("remark.pos", n=jobs.queue_position(job["id"])))


@st.fragment(run_every=2)
def queue_page():
    all_jobs = jobs.list_jobs()
    if not all_jobs:
        st.caption(t("queue.empty"))
        return
    active, waiting = jobs.active_job(), jobs.waiting_jobs()
    done = [j for j in all_jobs if j["state"] not in ("waiting",) + jobs.BUSY][:40]
    ordered = ([active] if active else []) + waiting + done
    with card("queue", t("queue.card"), t("queue.card_sub")):
        running = {}
        for j in all_jobs:
            if j.get("pipeline") and j["state"] in ("waiting",) + jobs.BUSY:
                running[j["pipeline"]["id"]] = j["pipeline"]
        for pid, p in running.items():
            done_n = sum(1 for x in jobs.pipeline_jobs(pid) if x["state"] == "done")
            c1, c2 = st.columns([5, 2], vertical_alignment="center")
            c1.markdown(t("queue.pipeline_line", name=p["name"], done=done_n, total=p["total"]))
            if c2.button(t("queue.cancel_pipeline"), key=f"stop-pl-{pid}", width="stretch"):
                jobs.cancel_pipeline(pid)
                st.rerun(scope="app")
        widths = [3.4, 1.35, 1.25, 1.9, 2.25, 1.9]
        with st.container(key="qhead"):
            head = st.columns(widths)
            for i, (c, name) in enumerate(zip(head, [t(f"queue.col.{k}") for k in ("name", "state", "elapsed", "progress", "remark", "action")])):
                c.markdown(f"<div style='text-align:center'><b>{name}</b></div>" if i == 1 else f"**{name}**", unsafe_allow_html=True)
        for job in ordered:
            # one framed row per job; the key carries the state for the coloured left edge (CSS st-key-qrow-<state>)
            cols = st.container(key=f"qrow-{job['state']}-{job['id']}").columns(widths, vertical_alignment="center")
            pipe = job.get("pipeline")
            pipe_text = "・" + t("queue.pipeline", name=pipe["name"], i=pipe["index"] + 1, n=pipe["total"]) if pipe else ""
            cols[0].markdown(f"{plain(job_title(job))}  \n<span class='act-note'>{KIND_TEXT.get(job['kind'], job['kind'])}・{(job.get('created') or '').replace('T', ' ').rstrip('Z')} UTC{plain(pipe_text)}</span>",
                             unsafe_allow_html=True)
            text, color = QUEUE_STATE.get(job["state"], (job["state"], "#8892a2"))
            cols[1].markdown(f"<div style='text-align:center;color:{color};font-weight:600'>{text}</div>", unsafe_allow_html=True)
            cols[2].markdown(elapsed_text(job))
            if job["state"] in ("queued", "running"):
                frac, ptext = progress_of(job, jobs.events(job["id"]))
                cols[3].progress(frac or 0.0, text=ptext)
            elif job["state"] == "done":
                cols[3].progress(1.0)
            else:
                cols[3].markdown("—")
            if job["state"] in jobs.BUSY:
                if cols[5].button(t("queue.force_end") if job["state"] == "lost" else t("queue.cancel"), key=f"stop-q-{job['id']}", width="stretch"):
                    jobs.cancel(job["id"])
            elif job["state"] == "waiting":
                if cols[5].button(t("queue.dequeue"), key=f"stop-dq-{job['id']}", width="stretch"):  # stop-: red (CSS)
                    jobs.cancel(job["id"])
                    st.rerun(scope="app")
            remark(job, cols[4])
    with st.expander(t("queue.details"), expanded=False):
        # the label carries no state: the dropdown does not refresh the text of an option that is already shown
        labels = {j["id"]: f"{job_title(j)}（{j.get('created', '').replace('T', ' ').rstrip('Z')} UTC）" for j in ordered}
        if st.session_state.get("job-select") not in labels:
            st.session_state.pop("job-select", None)
        job_id = st.selectbox(t("queue.job"), list(labels), format_func=labels.get, key="job-select")
        job_detail(job_id)


def copy_button(text, label=None):
    """A button that puts `text` on the clipboard without showing it (runs in a small iframe via st.iframe, or components.html on an
    older Streamlit; falls back to execCommand when the browser blocks navigator.clipboard there)."""
    label = label or t("copy.label")
    payload = json.dumps(text, ensure_ascii=False).replace("</", "<\\/")
    page = f"""<!doctype html>
<style>html, body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; }} body {{ padding-top: 3px; }}</style>
<button id="b" style="width:100%;height:38px;border-radius:8px;border:1px solid #4aa8ff;background:#4aa8ff;color:#08121f;
  font:600 14px system-ui,'Microsoft JhengHei',sans-serif;cursor:pointer">{label}</button>
<script>
const text = {payload}, b = document.getElementById('b'), label = b.textContent;
function fallback() {{ const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select();
  const ok = document.execCommand('copy'); document.body.removeChild(t); return ok; }}
b.onclick = async () => {{
  let ok = false;
  try {{ await navigator.clipboard.writeText(text); ok = true; }} catch (e) {{ ok = fallback(); }}
  b.textContent = ok ? {json.dumps(t('copy.done'), ensure_ascii=False)} : {json.dumps(t('copy.fail'), ensure_ascii=False)};
  setTimeout(() => b.textContent = label, 2000);
}};
</script>"""
    if hasattr(st, "iframe"):  # newer Streamlit: components.v1.html is deprecated (it logs a warning on every run)
        st.iframe(page, height=44)
    else:
        import streamlit.components.v1 as components
        components.html(page, height=44)


def job_summary_text(job):
    """A finished data / training / match job as Markdown to paste to an AI (None when there is nothing to say or its files are gone)."""
    result, state, kind = job.get("result") or {}, job["state"], job["kind"]
    try:
        if kind == "dump" and state in ("done", "cancelled") and result.get("rows"):
            return modelmeta.dump_summary(positions.read_meta(absolute(result["output"])), rel(result["output"]), plain(job_title(job)),
                                          modelmeta.job_seconds(job))
        if kind.startswith("train") and state == "done" and result.get("model"):
            return modelmeta.train_summary(modelmeta.read(absolute(result["model"]), include_local=False), os.path.basename(result["model"]))
        if kind == "match" and state == "done" and result.get("match"):
            return modelmeta.match_summary(result["match"], os.path.basename(str((job.get("spec") or {}).get("model", "")) or "model"))
    except (OSError, ValueError, KeyError):
        return None
    return None


def job_detail(job_id):
    job = jobs.read_job(job_id)
    if job is None:  # its folder was removed meanwhile
        st.caption(t("detail.gone"))
        return
    state = job["state"]
    evs = jobs.events(job_id)
    frac, text = progress_of(job, evs)
    if state == "waiting":
        frac, text = None, t("detail.waiting", n=jobs.queue_position(job_id))
    left, right = st.columns([2, 1])
    with left:
        if state == "waiting":
            st.info(text)
        elif frac is not None:
            st.progress(frac, text=f"{STATE_TEXT.get(state, state)}：{text}")
        elif state in ("queued", "running"):
            st.info(text)
        steps = [e for e in evs if e["stage"] in ("iteration", "epoch")]
        if steps:
            st.altair_chart(loss_chart([e["validLoss"] for e in steps], [e.get("iteration") or e.get("epoch") for e in steps], height=220), width="stretch")
    with right:
        st.markdown(f"**{t('detail.kind')}**: {KIND_TEXT.get(job['kind'], job['kind'])}")
        st.markdown(f"**{t('detail.state')}**: {STATE_TEXT.get(state, state)}")
        loaded = next((e for e in evs if e["stage"] == "loaded"), None)
        if loaded:
            st.markdown(f"**{t('detail.data')}**: " + t("detail.data_val", rows=f"{loaded['rows']:,}", valid=f"{loaded['validRows']:,}"))
        if job.get("started"):
            st.markdown(f"**{t('detail.start')}**: {job['started']}")
        if job.get("finished"):
            st.markdown(f"**{t('detail.end')}**: {job['finished']}")
        if state == "lost":
            st.warning(LOST_TEXT)
        if state in jobs.BUSY:
            if st.button(t("detail.force_end_job") if state == "lost" else t("detail.cancel_job"), key=f"stop-detail-{job_id}"):
                jobs.cancel(job_id)
            st.caption(t("detail.cancel_note"))
        if state == "waiting":
            if st.button(t("queue.dequeue"), key=f"stop-dequeue-{job_id}"):
                jobs.cancel(job_id)
        if state == "failed":
            st.error(scrub(job.get("error", "")))
        if state == "interrupted":
            st.warning(t("detail.interrupted"))
    result = job.get("result") or {}
    if state == "done" and job["kind"].startswith("train"):
        v = result["validation"]
        c1, c2, c3 = st.columns(3)
        c1.metric(t("detail.val_ce"), f"{v['crossEntropy']:.4f}")
        c2.metric(t("detail.val_mse"), f"{v['mse']:.4f}", help=t("detail.const_mse", x=f"{v['constantMse']:.4f}"))
        c3.metric("R²", f"{v['r2']:.3f}")
        st.success(t("detail.model_saved", path=rel(result["model"]), match=TAB_MATCH))
    if job["kind"] == "dump" and state in ("done", "cancelled") and result.get("rows"):
        st.success(t("detail.dump_result", status=t("detail.dump_cancelled" if state == "cancelled" else "detail.dump_done"), games=f"{result['games']:,}",
                     rows=f"{result['rows']:,}", path=rel(result["output"]), train=TAB_TRAIN))
    if job["kind"] == "match" and state == "done" and result.get("match"):
        m = result["match"]
        st.success(t("detail.match_done", win=f"{m['winShare']:.1%}", ci=f"{m['winShareCi95']:.1%}", games=m["games"], path=rel(result["output"])))
        seat, win, score = t("detail.col.seat"), t("detail.col.win"), t("detail.col.score")
        grid(pd.DataFrame([{seat: t("detail.seat.model"), win: m["winShare"], score: m["avgScore"]}] +
                          [{seat: o["seatId"] if o["strategy"] != "mcts" else (t("detail.seat.plain") if not o.get("valueModel") else t("detail.seat.withmodel")),
                            win: o["winShare"], score: o["avgScore"]} for o in m["others"]]),
             hide_index=True, column_config={win: st.column_config.NumberColumn(format="percent"),
                                             score: st.column_config.NumberColumn(format="%.1f")})
    summary = job_summary_text(job)
    if summary:
        c1, c2 = st.columns([1, 3], vertical_alignment="center")
        with c1:
            copy_button(scrub(summary))
        c2.caption(t("detail.copy_note"))
    with st.expander(t("detail.log"), expanded=state == "failed"):
        st.code(scrub(jobs.log_tail(job_id)) or t("detail.empty"), language=None)


# ---------------------------------------------------------------- 資料

def safe_name(name):
    return bool(name) and not any(c in name for c in '/\\:*?"<>| ')


def read_config(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def models_for(players):
    """Models with metadata for this player count."""
    out = []
    for p in model_files():
        meta = model_meta(p)
        if meta and meta.get("players") == players:
            out.append(p)
    return out


def write_config(path, cfg):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


# rule-based needs params.profile and is the same as the named strategies: not offered
_HIDDEN_STRATEGIES = {"rule-based"}
STRATEGY_TEXT = {n: t(f"strategy.{n}") for n in ("random", "guided-random", "mcts", "corn-shipper", "corn-to-premium", "harbor-rush", "build-first", "cheap-engine",
                                                      "wharf-rush", "wharf-premium", "corn-monopoly", "corn-monopoly-tiles", "corn-monopoly-hoard")}


@st.cache_data(show_spinner=False)
def strategy_names(mtime):
    """Registered strategies, read from the engine's registry (so the list never drifts from what the Runner accepts)."""
    path = os.path.join(ROOT, "Engine", "Strategies", "StrategyRegistry.cs")
    try:
        with open(path, encoding="utf-8") as f:
            names = re.findall(r'^\s*\["([a-z0-9-]+)"\]\s*=', f.read(), re.MULTILINE)
    except OSError:
        names = []
    names = [n for n in dict.fromkeys(names) if n not in _HIDDEN_STRATEGIES]
    return names or sorted(STRATEGY_TEXT)


def all_strategies():
    path = os.path.join(ROOT, "Engine", "Strategies", "StrategyRegistry.cs")
    return strategy_names(os.path.getmtime(path) if os.path.exists(path) else 0)


def parse_params(text):
    """'name=value, name=value' -> dict (numbers become numbers, like the Dashboard's parameter boxes). Raises ValueError."""
    out = {}
    for part in re.split(r"[,;]", text or ""):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(t("parse.format", part=part))
        k, v = (x.strip() for x in part.split("=", 1))
        if not k or not v:
            raise ValueError(t("parse.format", part=part))
        try:
            num = float(v)
            out[k] = int(num) if num.is_integer() and "." not in v else num
        except ValueError:
            out[k] = v
    return out


DEFAULT_CUSTOM = {4: ["cheap-engine", "build-first", "harbor-rush", "corn-to-premium"], 3: ["cheap-engine", "build-first", "harbor-rush"]}


def custom_seats(players):
    """One row per seat: strategy + its parameters. Returns (seats for the config, problems)."""
    names = all_strategies()
    seats, problems = [], []
    model_names = [t("custom.model_none")] + [os.path.basename(p) for p in models_for(players)]
    for i in range(players):
        default = DEFAULT_CUSTOM[players][i] if DEFAULT_CUSTOM[players][i] in names else names[0]
        c1, c2 = st.columns([2, 5])
        strat = c1.selectbox(t("custom.seat", n=i + 1), names, index=names.index(default), key=f"cu-s{i}",
                             format_func=lambda n: f"{n} ({STRATEGY_TEXT[n]})" if n in STRATEGY_TEXT and lang() != "zh-TW" else f"{n}（{STRATEGY_TEXT[n]}）" if n in STRATEGY_TEXT else n)
        with c2:
            if strat == "mcts":
                m1, m2, m3 = st.columns(3)
                sims = m1.number_input(t("custom.sims"), value=100, min_value=1, step=50, key=f"cu-sims{i}")
                model = m2.selectbox(t("custom.model"), model_names, key=f"cu-model{i}")
                leaf = m3.number_input("leafRollout", value=20 if model != model_names[0] else 0, min_value=0, step=5, key=f"cu-leaf{i}")
                params = {"simulations": int(sims)}
                if model != model_names[0]:
                    params["valueModel"] = rel(model_path(model))
                    params["leafRollout"] = int(leaf)  # also 0: the engine's default is 40 with a model on 4 players
            else:
                text = st.text_input(t("custom.params"), key=f"cu-p{i}", placeholder=t("custom.example"))
                try:
                    params = parse_params(text)
                except ValueError as e:
                    problems.append(t("custom.seat_param_error", n=i + 1, error=e))
                    params = {}
        seats.append({"id": f"{strat}-{i}", "strategy": strat, "params": params})
    return seats, problems


def tracked_by_git(paths):
    """Which of these files git tracks (built-in configs); empty when git is not available."""
    import subprocess
    try:
        out = subprocess.run(["git", "ls-files", "--", *[rel(p) for p in paths]], cwd=ROOT, capture_output=True, text=True, timeout=10)
        return set(out.stdout.split())
    except (OSError, subprocess.SubprocessError):
        return set()


def config_rows():
    """The data configs: built-in ml/data-configs, then local ml/local/data-configs."""
    rows = []
    files = sorted(glob.glob(os.path.join(ROOT, "ml", "data-configs", "*.json"))) + sorted(glob.glob(os.path.join(LOCAL_CONFIGS, "*.json")))
    for c in files:
        cfg = read_config(c)
        if cfg:
            rows.append({"設定檔": rel(c), "位置": "local" if os.path.dirname(os.path.abspath(c)) == os.path.abspath(LOCAL_CONFIGS) else "builtin",
                         "人數": cfg.get("players"), "局數": cfg.get("games"), "種子": cfg.get("seed"),
                         "座位": t("common.list").join(s.get("strategy", "") for s in cfg.get("seats", []))})
    return rows


def config_table(rows):
    """All data configs with checkboxes for deleting (inside the 管理設定檔 expander)."""
    shown = pd.DataFrame(rows)
    shown["設定檔"] = shown["設定檔"].map(os.path.basename)  # the folder is in the location column and the line below
    shown["位置"] = shown["位置"].map({"local": t("cfg.local"), "builtin": t("cfg.builtin")})
    shown = shown.rename(columns={"設定檔": t("cfg.col.config"), "位置": t("cfg.col.place"), "人數": t("cfg.col.players"), "局數": t("cfg.col.games"),
                                  "種子": t("cfg.col.seed"), "座位": t("cfg.col.seats")})
    picked = grid(shown.set_index(t("cfg.col.config")), on_select="rerun", selection_mode="multi-row", width="stretch", key=f"cfg-table-{delete_gen()}")
    chosen = [rows[i]["設定檔"] for i in picked.selection.rows]
    for i, folder in enumerate(dict.fromkeys(os.path.dirname(r["設定檔"]) for r in rows)):
        folder_line(folder + "/", f"configs-{i}")
    c1, c2 = st.columns([4, 2.2], vertical_alignment="center")
    tracked = tracked_by_git(chosen) if chosen else set()
    c1.caption(t("cfg.hint") + (("" if lang() == "zh-TW" else " ") + t("cfg.tracked", n=len(tracked)) if tracked else ""))
    with c2:
        delete_button("del-configs", t("del.button", n=len(chosen)), [absolute(c) for c in chosen], busy=busy_files("config"))


def selfplay_config(name, players, games, seed, sims, leaf, model_rel):
    """MCTS + value model at every seat (the data of an iteration)."""
    return {"schemaVersion": 1, "name": name, "players": players, "games": int(games), "seed": int(seed), "seatOrder": "random",
            "seats": [{"id": f"m{i}", "strategy": "mcts", "params": {"simulations": int(sims), "valueModel": model_rel, "leafRollout": int(leaf)}}
                      for i in range(players)],
            "output": {"perGameRecords": False}}


def data_tab():
    st.caption(t("dt.intro"))
    stamp = datetime.datetime.now().strftime("%m%d-%H%M")
    custom_problems = []
    with card("data-source", t("dt.card1")):
        mode = st.radio(t("dt.mode_label"), ["config", "custom", "selfplay"], format_func=lambda m: t(f"dt.mode.{m}"),
                        horizontal=True, label_visibility="collapsed")
        if mode == "config":
            rows = config_rows()
            if not rows:
                st.info(t("dt.no_configs"))
                return
            by_name = {r["設定檔"]: r for r in rows}
            config = st.selectbox(t("dt.which_config"), list(by_name),
                                  format_func=lambda c: t("dt.config_item", file=os.path.basename(c), players=by_name[c]["人數"], seats=by_name[c]["座位"]))
            folder_line(config, "config")
            with st.expander(t("dt.manage", n=len(rows))):
                config_table(rows)
            cfg = read_config(absolute(config))
            default_games, default_seed = int(cfg.get("games", 20000)), int(cfg.get("seed", 1))
            # the config's own output.dumpRate wins; without one, MCTS tables (self-play) default to 5%, the rest to 1%
            default_rate = float((cfg.get("output") or {}).get("dumpRate") or (0.05 if any(s_.get("strategy") == "mcts" for s_ in cfg.get("seats", [])) else 0.01))
            default_name = os.path.basename(config)[:-5]
            title_key, title_args = "job.title.dump_config", {}
        elif mode == "custom":
            st.caption(t("dt.custom_hint"))
            players = st.radio(t("dt.players"), [4, 3], horizontal=True, format_func=lambda n: t("match.players_n", n=n), key="cu-players")
            seats, custom_problems = custom_seats(players)
            has_mcts = any(s_["strategy"] == "mcts" for s_ in seats)
            default_games, default_seed = (2000 if has_mcts else 20000), int(datetime.datetime.now().strftime("%m%d%H"))
            default_rate = 0.05 if has_mcts else 0.01
            if has_mcts:
                st.caption(t("dt.mcts_slow"))
            default_name = f"{players}p-custom-{stamp}"
            title_key, title_args = "job.title.dump_custom", {"strategies": t("common.list").join(s_["strategy"] for s_ in seats)}
        else:
            players = st.radio(t("dt.players"), [4, 3], horizontal=True, format_func=lambda n: t("match.players_n", n=n), key="sp-players")
            cands = models_for(players)
            if not cands:
                st.info(t("dt.no_model", n=players))
                return
            model = st.selectbox(t("dt.which_model"), [os.path.basename(p_) for p_ in cands], index=len(cands) - 1)
            c1, c2 = st.columns(2)
            sims = c1.number_input(t("dt.sp_sims"), value=100, min_value=1, step=50, help=t("dt.sp_sims_help"))
            leaf = c2.number_input(t("dt.sp_leaf"), value=20, min_value=0, step=5)
            default_games, default_seed, default_rate = 4000, int(datetime.datetime.now().strftime("%m%d%H")), 0.05
            default_name = f"{players}p-selfplay-{model.rsplit('.', 1)[0].replace(f'{players}p-', '')}-{stamp}"
            title_key, title_args = "job.title.dump_selfplay", {"model": model}

    with card("data-run", t("dt.card2")):
        c1, c2, c3, c4, c5 = st.columns(5)
        # the defaults come from the chosen config: its name is part of the keys, so picking another config reloads them
        kk = mode + (config if mode == "config" else "")
        games = c1.number_input(t("dt.games"), value=default_games, min_value=1, step=1000, key=f"games-{kk}")
        seed = c2.number_input(t("dt.seed"), value=default_seed, step=1, key=f"seed-{kk}")
        rate = c3.number_input(t("dt.rate"), value=default_rate, min_value=0.0001, max_value=1.0, format="%g", key=f"rate-{kk}")
        threads = c4.number_input(t("dt.threads"), value=0, min_value=0, step=1, key=f"threads-{mode}")
        feature_versions = fingerprint.feature_versions()
        feature = c5.selectbox(t("dt.feature"), feature_versions, index=len(feature_versions) - 1, key="feature-version",
                               help=t("dt.feature_help"))
        if mode == "selfplay":
            st.caption(t("dt.sp_ref", games=f"{games:,}", hours=f"{games / 3600:.1f}"))
        name = st.text_input(t("dt.name"), value=default_name).strip()
        out = os.path.join(jobs.results_dir(), "ml", name + ".bin")
        exists = os.path.exists(out)
        overwrite = st.checkbox(t("dt.overwrite", name=name)) if exists else True
        writes_config = mode != "config"
        config_taken = writes_config and safe_name(name) and any(os.path.exists(os.path.join(d, name + ".json"))
                                                                  for d in (os.path.join(ROOT, "ml", "data-configs"), LOCAL_CONFIGS))
        name_problems = [p_ for p_ in [None if safe_name(name) else t("dt.p.name"),
                                       t("dt.p.config_taken", name=name) if config_taken else None] if p_]
        problems = name_problems + [p_ for p_ in [None if overwrite else t("dt.p.exists"),
                                                  t("dt.p.pending") if pending_output(rel(out)) else None] if p_] + custom_problems

        def new_config():
            if mode == "custom":
                return {"schemaVersion": 1, "name": name, "players": players, "games": int(games), "seed": int(seed),
                        "seatOrder": "random", "seats": seats, "output": {"perGameRecords": False}}
            return selfplay_config(name, players, games, seed, sims, leaf, rel(model_path(model)))

        # what this run would produce, by recipe: compared with what already exists under this name and under other names
        eff = {**cfg, "games": int(games), "seed": int(seed)} if mode == "config" else new_config()
        new_recipe = fingerprint.planned_dump_recipe(eff, float(rate), int(feature))
        new_fp = fingerprint.fingerprint(new_recipe)
        known = [d for d in list_dumps() if "_fp" in d]
        old_recipe = next((d["_recipe"] for d in known if d["path"] == rel(out)), None)
        same_name_notice(t("noun.data"), exists, old_recipe, new_recipe, users=models_using(rel(out)) if exists else ())
        twins = [d["來源"] for d in known if d["_fp"] == new_fp and d["path"] != rel(out)]
        if twins:
            st.info(t("dt.twins", list=t("common.list").join(f"`{name_}`" for name_ in twins)))
        if exists and reader_problem(rel(out)):
            problems.append(reader_problem(rel(out)))

        if mode == "custom":
            save_problems = name_problems + custom_problems
            b1, b2 = st.columns([2.2, 5], vertical_alignment="center")
            with b1:
                save = st.button(t("dt.save"), key="save-config", disabled=bool(save_problems), width="stretch")
            with b2:
                st.markdown(f'<span class="act-err">{t("dt.save_cannot", reasons=t("common.sep").join(plain(x) for x in save_problems))}</span>' if save_problems
                            else f'<span class="act-note">{t("dt.save_note", name=plain(name))}</span>', unsafe_allow_html=True)
            if save:
                write_config(os.path.join(LOCAL_CONFIGS, name + ".json"), new_config())
                st.session_state["job-started"] = t("dt.saved", name=name)
                st.rerun()

        if action_row(t("dt.start"), "start-dump", problems):
            if mode == "config":
                spec_config = config
            else:
                spec_config = rel(os.path.join(LOCAL_CONFIGS, name + ".json"))
                write_config(absolute(spec_config), new_config())  # kept with the other data configs: reusable and reproducible
            start_job("dump", t(title_key, name=name, **title_args),
                      {"config": spec_config, "out": rel(out), "rate": float(rate), "games": int(games), "seed": int(seed),
                       "threads": int(threads), "featureVersion": int(feature)}, title_key, name=name, **title_args)

    with card("data-list", t("dt.card3")):
        dumps = [d for d in list_dumps() if "error" not in d and not d.get("writing")]
        if dumps:
            df = table_view(dumps).set_index(pd.Index([os.path.basename(d["path"]) for d in dumps], name=t("dump.col.file")))
            picked = grid(df, on_select="rerun", selection_mode="multi-row", width="stretch", key=f"dumps-manage-{delete_gen()}",
                          column_config=dump_column_config())
            chosen = [dumps[i] for i in picked.selection.rows]
            folder_line(os.path.dirname(dumps[0]["path"]) + "/", "data-list")
            c1, c2 = st.columns([4, 2.2], vertical_alignment="center")
            c1.caption(t("dt.delete_hint", page=TAB_TRAIN))
            with c2:
                delete_button("del-dumps", t("del.button", n=len(chosen)), [absolute(d["path"]) for d in chosen],
                              extra_suffixes=(".json",), busy=busy_files("data"))
        else:
            st.caption(t("dt.none"))


# ---------------------------------------------------------------- 對戰驗證

MATCH_TABLES = {key: t(f"match.table.{key}") for key in ("default", "hand", "model")}


def match_seats(table, players, model, sims, leaf, base_sims, rival=None, model_rel=None):
    """The seats of a match: the model under test first. table "model": a second MCTS seat plays another value model (`rival`, with
    `base_sims` simulations and the same leafRollout), so the two models are compared on the same table. `model_rel`: the model's path
    when it does not exist yet (a model a pipeline is about to train)."""
    # leafRollout is always written, also 0: the engine's default is 40 with a model on 4 players, so leaving it out would not mean 0
    me = {"id": "value", "strategy": "mcts", "params": {"simulations": sims, "valueModel": model_rel or rel(model_path(model)), "leafRollout": leaf}}
    hand = lambda name: {"id": name, "strategy": name, "params": {}}  # noqa: E731
    if table == "model":
        other = {"id": "rival", "strategy": "mcts", "params": {"simulations": base_sims, "valueModel": rel(model_path(rival)), "leafRollout": leaf}}
        rest = ["cheap-engine", "build-first"] if players == 4 else ["cheap-engine"]
        return [me, other] + [hand(n) for n in rest]
    if table == "default":
        base = {"id": "mcts-default", "strategy": "mcts", "params": {"simulations": base_sims}}
        rest = ["cheap-engine", "build-first"] if players == 4 else ["cheap-engine"]
        return [me, base] + [hand(n) for n in rest]
    rest = ["corn-shipper", "corn-to-premium", "build-first"] if players == 4 else ["corn-shipper", "build-first"]
    return [me] + [hand(n) for n in rest]


def match_default_name(model, sims, leaf, table, rival, base_sims, seed):
    """The default result name of a match, e.g. 4p-v2-s300-leaf40-vs-default-seed9191."""
    stem = model.rsplit(".", 1)[0]
    versus = {"default": "default", "hand": "hand", "model": rival.rsplit(".", 1)[0] if rival else ""}[table]
    return (f"{stem}-s{int(sims)}{f'-leaf{int(leaf)}' if leaf else ''}-vs-{versus}{f'{int(base_sims)}' if table == 'default' and base_sims != 300 else ''}"
            f"{f'-s{int(base_sims)}' if table == 'model' and base_sims != sims else ''}-seed{int(seed)}")


def _match_body():
    st.caption(t("match.intro"))
    players = st.radio(t("match.players"), [4, 3], horizontal=True, format_func=lambda n: t("match.players_n", n=n), key="m-players")
    cands = models_for(players)
    if not cands:
        st.info(t("match.no_model", n=players))
        return
    names = [os.path.basename(p) for p in cands]
    model = st.selectbox(t("match.model"), names, index=len(names) - 1, key="m-model")
    table = st.radio(t("match.opponent"), list(MATCH_TABLES), format_func=MATCH_TABLES.get, horizontal=True, key="m-table")
    rival = None
    if table == "model":
        others = [n for n in names if n != model]
        if not others:
            st.info(t("match.only_one", n=players))
            return
        # open on the strongest other model (best win share against the original MCTS)
        best = lambda n: (best_vs_default(model_meta(model_path(n))) or {}).get("winShare", -1) if model_meta(model_path(n)) else -1  # noqa: E731
        rival = st.selectbox(t("match.rival"), others, index=others.index(max(others, key=best)), key="m-rival")
    c1, c2, c3, c4 = st.columns(4)
    sims = c1.number_input(t("match.sims"), value=300, min_value=1, step=10)
    leaf = c2.number_input(t("match.leaf_both") if table == "model" else t("match.leaf"), value=40 if players == 4 else 0, min_value=0, step=5, key=f"m-leaf-{players}")
    base_sims = c3.number_input(t("match.base_model") if table == "model" else t("match.base_orig"), value=300, min_value=1, step=10, disabled=table == "hand")
    seed = c4.number_input(t("match.seed"), value=9191, step=1)
    perm = 24 if players == 4 else 6
    c5, c6 = st.columns(2)
    games = c5.number_input(t("match.games", perm=perm), value={"default": 240, "model": 480}.get(table, 408), min_value=perm, step=perm)
    threads = c6.number_input(t("match.threads"), value=0, min_value=0, step=1, key="m-threads")
    seats = match_seats(table, players, model, int(sims), int(leaf), int(base_sims), rival)
    st.caption(t("match.table_line", seats=t("common.list").join((t("match.seat_model") if s["id"] == "value" else t("match.seat_rival", rival=rival, n=int(base_sims)) if s["id"] == "rival"
                                                                    else t("match.orig_mcts") if s["strategy"] == "mcts" else s["strategy"]) for s in seats),
                                   lo=f"{int(games) * 0.6 / 60:.0f}", hi=f"{int(games) * 1.2 / 60:.0f}"))
    default_name = match_default_name(model, sims, leaf, table, rival, base_sims, seed)
    name = st.text_input(t("match.name"), value=default_name).strip()
    out = os.path.join(jobs.results_dir(), "ml", name + ".json")
    exists = os.path.exists(out)
    # recipe of this match (the value model counts by file content), compared with the result under this name and with
    # the matches already recorded for the model
    new_recipe = fingerprint.planned_match_recipe({"players": players, "games": int(games), "seed": int(seed),
                                                   "seatOrder": "balanced", "seats": seats})
    new_fp = fingerprint.fingerprint(new_recipe)
    old_recipe = None
    if exists:
        try:
            with open(out, encoding="utf-8") as f:
                old_recipe = fingerprint.result_recipe(json.load(f))
        except (OSError, ValueError, KeyError, TypeError):
            old_recipe = None
    same_name_notice(t("noun.match_result"), exists, old_recipe, new_recipe)
    done_meta = model_meta(model_path(model))
    twins = [m for m in (done_meta or {}).get("matches", []) if m.get("fingerprint") == new_fp and m.get("result") != rel(out)]
    if twins:
        st.info(t("match.twins", list=t("common.list").join(t("match.twin_item", config=m["config"], win=f"{m['winShare']:.1%}") for m in twins)))
    overwrite = st.checkbox(t("match.overwrite", name=name)) if exists else True
    problems = [p for p in [None if safe_name(name) else t("match.p.name"),
                            None if games % perm == 0 else t("match.p.games", perm=perm),
                            None if overwrite else t("match.p.exists"),
                            t("match.p.pending") if pending_output(rel(out)) else None] if p]
    if action_row(t("match.start"), "start-match", problems):
        cfg = {"schemaVersion": 1, "name": name, "players": players, "games": int(games), "seed": int(seed),
               "seatOrder": "balanced", "seats": seats, "output": {"perGameRecords": False}}
        if threads:
            cfg["parallelism"] = {"maxDegree": int(threads)}
        config = rel(os.path.join(LOCAL_MATCHES, name + ".json"))
        write_config(absolute(config), cfg)
        title_key = f"job.title.match_{table}"
        start_job("match", t(title_key, model=model, sims=int(sims), rival=rival, name=name),
                  {"config": config, "out": rel(out), "model": rel(model_path(model))}, title_key, model=model, sims=int(sims), rival=rival, name=name)
    meta = model_meta(model_path(model))
    if meta and meta.get("matches"):
        st.markdown(t("match.existing", model=model))
        grid(matches_frame(meta, model_path(model)), hide_index=True, width="stretch",
                     column_config=MATCH_COLUMNS)
        match_summary_box(meta, model_path(model), f"match-{model}")


# ---------------------------------------------------------------- 模型詳細資料、模型清單

def models_table(paths):
    col = lambda key: t(f"mlist.col.{key}")  # noqa: E731
    places = {"official": "git", "local": "local"}
    rows = []
    for p in paths:
        meta = model_meta(p)
        name = os.path.basename(p)
        if not meta:
            rows.append({col("model"): name, col("place"): places[place_of(p)], col("kind"): "LightGBM" if p.endswith(".txt") else "MLP", col("note"): t("mlist.no_meta")})
            continue
        best = best_vs_default(meta)
        v = meta.get("validation") or {}
        rows.append({
            col("model"): name, col("place"): places[place_of(p)], col("kind"): KIND_TEXT.get(meta["kind"], meta["kind"]), col("players"): meta["players"],
            col("feature"): meta.get("featureVersion"),
            col("rows"): sum(d["rows"] for d in meta["data"]),
            col("selfplay"): t("common.list").join(sorted({os.path.basename(m) for d in meta["data"] for m in d.get("valueModels", [])})),
            col("r2"): v.get("r2"), col("ce"): v.get("crossEntropy"),
            col("matches"): len(meta.get("matches", [])),
            col("best"): best["winShare"] if best else None,
            col("hash"): fingerprint.short(meta.get("fingerprint")) or "—",
            col("rules"): fingerprint.rules_name(meta.get("rulesRevision", 1)),
            col("note"): t("mlist.params_backfilled") if "note" in meta.get("params", {}) else (t("mlist.old_record") if not meta.get("fingerprint") else ""),
        })
    df = pd.DataFrame(rows)
    # text columns so that missing values read "—" instead of Streamlit's grey "None"
    fmt = {col("r2"): "{:.3f}", col("ce"): "{:.4f}", col("best"): "{:.1%}", col("rows"): "{:,.0f}", col("players"): "{:.0f}", col("matches"): "{:.0f}", col("feature"): "{:.0f}"}
    for name, f in fmt.items():
        if name in df:
            df[name] = [f.format(v) if v is not None and v == v else "—" for v in df[name]]
    return df.fillna("")


def match_note(m, current_sha):
    """Why an old result may no longer describe the model / engine of today."""
    notes = []
    if m.get("modelSha256") and current_sha and m["modelSha256"] != current_sha:
        notes.append(t("match.note.model_changed"))
    stale = entry_stale(m.get("rulesRevision", 1), m.get("ruleset"), m.get("revisions"),
                        [o.get("strategy") for o in m.get("others", [])] + ["mcts"])
    if stale:
        notes.append(t("match.note.old") + t("common.sep").join(stale))
    return t("common.sep").join(notes)


# match tables (model page and match page): short columns centred
MATCH_COLUMNS = {
    t("mt.win"): st.column_config.NumberColumn(format="percent"),
    "±95%": st.column_config.NumberColumn(format="percent"),
    t("mt.score"): st.column_config.NumberColumn(format="%.1f", alignment="center"),
    "leafRollout": st.column_config.NumberColumn(alignment="center"),
    t("mt.games"): st.column_config.NumberColumn(alignment="center"),
    t("mt.seed"): st.column_config.NumberColumn(alignment="center", format="%d"),
    t("mt.store"): st.column_config.TextColumn(alignment="center"),
    "hash": st.column_config.TextColumn(alignment="center"),
}


def matches_frame(meta, model_file=None):
    current_sha = fingerprint.file_sha256(model_file) if model_file and os.path.exists(model_file) else None
    official = bool(model_file) and place_of(model_file) == "official"
    rows = []
    for m in meta.get("matches", []):
        rows.append({t("mt.config"): m.get("config"), t("mt.opponent"): describe_match(m), "leafRollout": m.get("leafRollout", 0) or 0,
                     t("mt.games"): m["games"], t("mt.seed"): m["seed"],
                     t("mt.win"): m["winShare"], "±95%": m.get("winShareCi95"), t("mt.score"): m["avgScore"],
                     t("mt.oppwin"): t("common.list").join(f"{o['strategy'] if not o.get('valueModel') else t('detail.seat.withmodel')} {o['winShare']:.1%}" for o in m["others"]),
                     # where the record is kept: in the model's tracked .meta.json (git) or only on this machine
                     t("mt.store"): "git" if official and not m.get("local") else "local",
                     t("mt.result"): m["result"], "hash": fingerprint.short(m.get("fingerprint")) or "—", t("mt.note"): match_note(m, current_sha)})
    return pd.DataFrame(rows)


def match_summary_box(meta, model_file, key):
    """'複製摘要給 AI': one match record (or all of them) as short Markdown, copied by a button (the text itself is not shown)."""
    matches = meta.get("matches") or []
    if not matches:
        return
    current_sha = fingerprint.file_sha256(model_file) if os.path.exists(model_file) else None
    labels = [t("match.pick_item", name=m.get("config") or m["result"], games=m["games"]) for m in matches]
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    pick = c1.selectbox(t("match.pick"), [t("match.pick_all")] + labels, key=f"summary-pick-{key}",
                        help=t("match.pick_help"))
    chosen = matches if pick == t("match.pick_all") else [matches[labels.index(pick)]]
    name = os.path.basename(model_file)
    with c2:
        copy_button("\n\n".join(modelmeta.match_summary(m, name, match_note(m, current_sha)) for m in chosen))


def flat_params(meta):
    return {k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in (meta.get("params") or {}).items()}


def move_buttons(path):
    """Make official (local -> ml/models, then commit it) and move to local (an official-folder model git does not track)."""
    name = os.path.basename(path)
    if place_of(path) == "local":
        c1, c3, c2 = st.columns([2.2, 2.2, 5], vertical_alignment="center")
        with c3:
            if st.button(t("md.rename"), key=f"rename-{name}", width="stretch"):
                rename_dialog(path)
        with c1:
            with st.popover(t("md.promote"), width="stretch"):
                st.markdown(t("md.promote_text", name=name))
                if st.button(t("md.promote_ok"), type="primary", key=f"promote-{name}"):
                    try:
                        modelmeta.move_model(path, MODELS_DIR)
                        st.session_state["job-started"] = t("md.promoted", name=name)
                        st.cache_data.clear()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        c2.markdown(f'<span class="act-note">{t("md.local_note")}</span>', unsafe_allow_html=True)
    elif not tracked_by_git([path]):
        c1, c2 = st.columns([2.2, 5], vertical_alignment="center")
        with c1:
            if st.button(t("md.demote"), key=f"demote-{name}", width="stretch"):
                try:
                    modelmeta.move_model(path, LOCAL_MODELS)
                    st.session_state["job-started"] = t("md.demoted", name=name)
                    st.cache_data.clear()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        c2.markdown(f'<span class="act-note">{t("md.demote_note")}</span>', unsafe_allow_html=True)


def model_name_users(path):
    """What still names this model by its file name: data whose self-play seats used it, and configs that point at it."""
    name = os.path.basename(path)
    dumps = [d["來源"] for d in list_dumps() if "_meta" in d and any(
        os.path.basename(str(((s_.get("params") or {}).get("valueModel")) or "")) == name for s_ in d["_meta"].get("seats", []))]
    configs = []
    for folder in (os.path.join(ROOT, "ml", "data-configs"), LOCAL_CONFIGS, LOCAL_MATCHES):
        for c in sorted(glob.glob(os.path.join(folder, "*.json"))):
            cfg = read_config(c) or {}
            if any(os.path.basename(str(((s_.get("params") or {}).get("valueModel")) or "")) == name for s_ in cfg.get("seats", [])):
                configs.append(rel(c))
    return dumps, configs


@st.dialog(t("md.rename_title"))
def rename_dialog(path):
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1]
    new = st.text_input(t("md.rename_new", ext=ext), value=name[:-len(ext)], key=f"rename-new-{name}").strip()
    if new.endswith(ext):
        new = new[:-len(ext)]
    problems = []
    if not new or any(c in new for c in modelmeta.INVALID_NAME_CHARS):
        problems.append(t("md.rn.p.name"))
    elif new + ext == name:
        problems.append(t("md.rn.p.same"))
    elif model_name_taken(new + ext):
        problems.append(t("md.rn.p.taken", name=new + ext))
    busy = pending_readers(rel(path)) + ([job_title(j) for j in jobs.list_jobs() if j["state"] in ("waiting",) + jobs.BUSY
                                          and str(j.get("spec", {}).get("out", "")).replace("\\", "/") == rel(path)])
    if busy:
        problems.append(t("md.rn.p.busy", title=busy[0]))
    st.caption(t("md.rn.caption", name=name))
    refs = modelmeta.model_references(path)
    if refs["meta"]:
        st.info(t("md.rn.refs", list="\n".join(f"- `{rel(p)}`" for p in refs["meta"])))
    if refs["official"]:
        st.caption(t("md.rn.official", list=t("common.list").join(f"`{rel(p)}`" for p in refs["official"])))
    dumps, configs = model_name_users(path)
    local_configs = [c for c in refs["configs"] if rel(c) in configs]
    picked = []
    if local_configs:
        st.markdown(t("md.rn.cfgs"))
        picked = [c for c in local_configs if st.checkbox(f"`{rel(c)}`", value=True, key=f"rename-cfg-{name}-{rel(c)}")]
    stale = [c for c in configs if c not in {rel(x) for x in picked}]
    if dumps or stale:
        st.warning(t("md.rn.stale", items="\n".join(t("md.rn.item_data", d=d) for d in dumps) + ("\n" if dumps and stale else "")
                                   + "\n".join(t("md.rn.item_cfg", c=c) for c in stale)))
    if problems:
        st.markdown(f'<span class="act-err">{t("md.rn.cannot", reasons=t("common.sep").join(plain(x) for x in problems))}</span>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button(t("queue.cancel"), key=f"rename-cancel-{name}", width="stretch"):
        st.rerun()
    if c2.button(t("md.rn.ok"), type="primary", key=f"rename-ok-{name}", width="stretch", disabled=bool(problems)):
        try:
            target = modelmeta.rename_model(path, new, configs=picked)
            st.session_state["job-started"] = t("md.rn.done", name=name, new=os.path.basename(target))
            st.session_state["model-pick"] = os.path.basename(target)
            st.cache_data.clear()
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def model_data_table(meta):
    """The training data of a model with the same columns, in the same order, as the table that picks training data on the
    training page: file, players, games, rows, sampling rate, feature version, size, strategies (an MCTS seat names its value
    model), hash, rules version, engine commit. Players and feature version are the model's (all its data shares them); size and
    commit come from the dump on disk, only when it still is the same recipe (hash) as when the model was trained."""
    on_disk = {d["path"]: d for d in list_dumps() if "_fp" in d}
    col = lambda key: t(f"dump.col.{key}")  # noqa: E731
    rows = []
    for d in meta["data"]:
        path = d["path"].replace("\\", "/")
        disk = on_disk.get(path)
        same = disk is not None and disk["_fp"] == d.get("fingerprint")
        models = [os.path.splitext(os.path.basename(m))[0] for m in d.get("valueModels", [])]
        strategies = [f"{x}({t('common.list').join(models)})" if x == "mcts" and models else x for x in d.get("strategies", []) if x]
        rows.append({col("file"): os.path.basename(path), col("players"): str(meta["players"]), col("games"): d["games"], col("rows"): d["rows"],
                     col("rate"): d["rate"], col("feature"): str(meta["featureVersion"]), col("size"): disk["大小 MB"] if same else "—",
                     col("strategies"): t("common.list").join(dict.fromkeys(strategies)), "hash": fingerprint.short(d.get("fingerprint")) or "—",
                     col("rules"): fingerprint.rules_name(d.get("rulesRevision", 1), d.get("ruleset")),
                     col("commit"): disk["引擎 commit"] if same else "—"})
    return pd.DataFrame(rows)


def model_detail(path):
    meta = model_meta(path)
    name = os.path.basename(path)
    move_buttons(path)
    if not meta:
        st.warning(t("md.no_meta", name=name))
        return
    v = meta.get("validation") or {}
    best = best_vs_default(meta)
    st.markdown(version_tiles([(t("mlist.col.kind"), KIND_TEXT.get(meta["kind"], meta["kind"])),
                               (t("mlist.col.rows"), f"{sum(d['rows'] for d in meta['data']):,}"),
                               ("R²", f"{v['r2']:.3f}" if v.get("r2") is not None else "—", METRIC_HELP["R²"]),
                               (t("mlist.col.ce"), f"{v['crossEntropy']:.4f}" if v.get("crossEntropy") is not None else "—", METRIC_HELP["交叉熵"]),
                               (t("mlist.col.best"), f"{best['winShare']:.1%}" if best else "—")], centre=True), unsafe_allow_html=True)
    st.caption(t("md.best_from", desc=describe_match(best)) if best else t("md.no_best"))

    st.markdown(t("md.matches_title"))
    mf = matches_frame(meta, path)
    if mf.empty:
        st.caption(t("md.no_matches"))
    else:
        grid(mf, hide_index=True, width="stretch",
                     column_config=MATCH_COLUMNS)
        st.caption(t("md.dash_note", url=DASHBOARD_URL))
        match_summary_box(meta, path, f"detail-{name}")

    st.markdown(t("md.data_title"))
    df = model_data_table(meta)
    grid(df, hide_index=True, width="stretch", column_config=dump_column_config())
    if meta.get("data"):
        folder_line(os.path.dirname(meta["data"][0]["path"].replace("\\", "/")) + "/", f"model-data-{name}")

    left, right = st.columns(2)
    with left:
        st.markdown(t("md.params_title"))
        grid(pd.DataFrame(list(flat_params(meta).items()), columns=[t("md.pcol.param"), t("md.pcol.value")]).astype(str),
                     hide_index=True, width="stretch")
    with right:
        st.markdown(t("md.valid_title"))
        if v.get("byRound"):
            grid(pd.DataFrame(v["byRound"]).rename(columns={"rounds": t("md.vcol.rounds"), "rows": t("md.vcol.rows"), "mse": "MSE"}),
                         hide_index=True, width="stretch")
        else:
            st.caption(t("md.no_record"))
        st.caption(t("md.valid_note"))

    curve = (meta.get("training") or {}).get("validLossCurve")
    feats = meta.get("topFeatures") or []
    left, right = st.columns(2)
    with left:
        st.markdown(t("md.curve_title"))
        if curve:
            st.altair_chart(loss_chart(curve, height=240), width="stretch")
        else:
            st.caption(t("md.no_curve"))
    with right:
        st.markdown(t("md.feat_title"))
        if feats:
            fd = pd.DataFrame(feats[:20])
            chart = alt.Chart(fd).mark_bar().encode(x=alt.X("gain:Q", title="gain"),
                                                    y=alt.Y("name:N", sort="-x", title=None),
                                                    tooltip=["name", alt.Tooltip("gain:Q", format=",.0f")])
            st.altair_chart(chart.properties(height=420), width="stretch")
        else:
            st.caption(t("md.no_feat"))
    env = meta.get("environment") or {}
    env_text = t("md.env_missing") if "note" in env else "・".join(f"{k} {val}" for k, val in env.items())
    st.caption(t("md.foot", version=meta["featureVersion"], count=meta["featureCount"], created=meta.get("created") or t("mlist.backfilled"), env=env_text)
               + (t("md.foot_hash", hash=fingerprint.short(meta["fingerprint"]), rules=fingerprint.rules_name(meta.get("rulesRevision", 1), (meta.get("data") or [{}])[0].get("ruleset")))
                  if meta.get("fingerprint") else t("md.foot_old")))
    stale = model_stale(meta)
    if stale:
        st.warning(t("md.stale_warn", notes=t("common.sep").join(stale)))


def compare(paths):
    """Side by side, as a wrapping table (no scrollbar). Result rows mark the best model: the highest value, the lowest
    cross-entropy. Parameter rows mark the ones that differ."""
    metas = {os.path.basename(p): model_meta(p) for p in paths}
    names = list(metas)

    def best_cells(values, higher=True):
        nums = [x for x in values if x is not None]
        top = (max(nums) if higher else min(nums)) if len(nums) >= 2 and len(set(nums)) > 1 else None
        return ["c best" if x is not None and x == top else "c" for x in values]

    def metric_row(label, get, fmt, higher=True):
        values = [get(metas[n]) if metas[n] else None for n in names]
        kinds = best_cells(values, higher)
        return [(label, "l nw")] + [(fmt(x) if x is not None else "—", k) for x, k in zip(values, kinds)] + [("", "c")]

    rows = [
        metric_row(t("mlist.col.best"), lambda m: best_vs_default(m)["winShare"] if best_vs_default(m) else None, lambda x: f"{x:.1%}"),
        metric_row("R²", lambda m: (m.get("validation") or {}).get("r2"), lambda x: f"{x:.3f}"),
        metric_row(t("md.cmp.ce"), lambda m: (m.get("validation") or {}).get("crossEntropy"), lambda x: f"{x:.4f}", higher=False),
        metric_row(t("mlist.col.rows"), lambda m: sum(d["rows"] for d in m["data"]), lambda x: f"{x:,}"),
        [(t("md.cmp.source"), "l nw")] + [(t("common.list").join(d["source"] for d in metas[n]["data"]) if metas[n] else "—", "l") for n in names] + [("", "c")],
    ]
    keys = []
    for m in metas.values():
        for k in flat_params(m or {}):
            if k not in keys:
                keys.append(k)
    for k in keys:
        vals = [str(flat_params(metas[n] or {}).get(k, "—")) for n in names]
        rows.append([(k, "l nw")] + [(x, "c") for x in vals] + [("●" if len(set(vals)) > 1 else "", "c")])
    st.markdown(version_table([t("md.cmp.item")] + names + [t("md.cmp.diff")], rows, css="cmp"), unsafe_allow_html=True)
    st.caption(t("md.cmp.note"))


def _models_body():
    paths = model_files()
    if not paths:
        st.info(t("md.none"))
        return
    by_name = {os.path.basename(p): p for p in paths}
    mode = st.radio(t("md.view"), ["single", "compare"], horizontal=True, format_func=lambda m: t(f"md.view.{m}"), key="models-view")
    if mode == "single":
        # open on the strongest model (best win share against the original MCTS)
        scores = [(best_vs_default(model_meta(p))["winShare"] if model_meta(p) and best_vs_default(model_meta(p)) else -1) for p in paths]
        if st.session_state.get("model-pick") not in by_name:
            st.session_state.pop("model-pick", None)  # opens on the strongest model; a rename selects the renamed one
        # passing index while the key already holds a value makes Streamlit warn: only on the first draw
        start = {} if "model-pick" in st.session_state else {"index": scores.index(max(scores))}
        with st.container(key="modelpick"):  # a bigger label and dropdown (CSS .st-key-modelpick)
            name = st.selectbox(t("md.pick"), list(by_name), key="model-pick", **start)
        model_detail(by_name[name])
    else:
        names = st.multiselect(t("md.pick_many"), list(by_name), max_selections=4)
        if len(names) >= 2:
            compare([by_name[n] for n in names])
        else:
            st.caption(t("md.pick_hint"))


def match_tab():
    with card("match", t("match.card")):
        _match_body()


def model_list_page():
    with card("models-list", t("mlist.card"), t("mlist.card_sub", page=TAB_MODELS)):
        models_list()


def models_tab():
    with card("models", t("md.card")):
        _models_body()
    with card("models-metrics", t("md.metrics_card")):
        st.markdown(version_table([t("md.m.col.metric"), t("md.m.col.meaning"), t("md.m.col.range"), t("md.m.col.read")], [
            [("R²", "l nw"), (t("md.m.r2.meaning"), "l"), (t("md.m.r2.range"), "l nw"), (t("md.m.r2.read"), "l")],
            [(t("mlist.col.ce"), "l nw"), (t("md.m.ce.meaning"), "l"), (t("md.m.ce.range"), "l nw"), (t("md.m.ce.read"), "l")],
        ], css="doc"), unsafe_allow_html=True)
        st.caption(t("md.m.note"))


def models_list():
    """Every model, with quick filters (place: git / local, kind, player count, rules version; each in its own box); empty
    filter = all. Selected rows can be deleted (red button)."""
    paths = model_files()
    if not paths:
        return
    table = models_table(paths)
    col = lambda key: t(f"mlist.col.{key}")  # noqa: E731
    rules_opts = sorted({r for r in table[col("rules")] if r}) if col("rules") in table else []
    widths = [1.1, 1.5, 1.5, 0.6 + 0.9 * len(rules_opts), 2]
    cols = st.columns(widths)
    boxes = []
    for c, name in zip(cols, ("place", "kind", "players", "rules")):
        boxes.append(c.container(key=f"filterbar-mf-{name}"))  # one box per category (CSS .st-key-filterbar*)
    places = boxes[0].pills(t("mlist.place"), ["git", "local"], selection_mode="multi", key="mf-place")
    kinds = boxes[1].pills(t("mlist.kind"), ["LightGBM", "MLP"], selection_mode="multi", key="mf-kind")
    players = boxes[2].pills(t("mlist.players"), ["3", "4"], selection_mode="multi", key="mf-players", format_func=lambda n: t("match.players_n", n=n))
    rules = boxes[3].pills(t("mlist.rules"), rules_opts, selection_mode="multi", key="mf-rules")
    keep = (table[col("place")].isin(places or ["git", "local"]) & table[col("kind")].isin(kinds or ["LightGBM", "MLP"])
            & table[col("players")].isin(players or ["3", "4"]))
    if rules:  # models without metadata have no rules version: they only show while no rules filter is selected
        keep &= table[col("rules")].isin(rules)
    shown = table[keep]
    shown_paths = [p for p, k in zip(paths, keep) if k]
    if shown.empty:
        st.caption(t("mlist.none"))
        return
    centred = {c: st.column_config.TextColumn(c, alignment="center") for c in (col("players"), col("feature"), col("rules"), col("r2"), col("ce"), col("matches"), col("best"))
               if c in shown}
    # a selection is by row number: the filters and the deletion counter are part of the key
    picked = grid(shown, hide_index=True, width="stretch", column_config=centred, on_select="rerun", selection_mode="multi-row",
                  key=f"models-list-{delete_gen()}-{'.'.join(places or [])}-{'.'.join(kinds or [])}-{'.'.join(players or [])}-{'.'.join(rules or [])}")
    chosen = [shown_paths[i] for i in picked.selection.rows]
    st.caption(t("mlist.footer", shown=len(shown), total=len(table)))
    busy = {f for j in jobs.list_jobs() if j["state"] in ("waiting",) + jobs.BUSY for f in job_reads(j)}
    busy |= busy_files("out")  # a training job that is writing it
    files = [p for m in chosen for p in [m, os.path.join(modelmeta.local_records_dir(), os.path.basename(m) + ".matches.json")]
             if os.path.exists(p)]  # the model and the match records kept beside it (official models' records are local)
    c1, c2 = st.columns([4, 2.2], vertical_alignment="center")
    c1.caption(t("mlist.delete_hint") + (" " + t("mlist.delete_official") if any(place_of(m) == "official" for m in chosen) else ""))
    with c2:
        delete_button("del-models", t("del.button", n=len(chosen)), files, extra_suffixes=(".meta.json", ".check.txt"), busy=busy)


# ---------------------------------------------------------------- hash 說明、版本控管

def _option_names(keys):
    def one(k):
        if k not in PARAM_DEFAULTS:
            return f"`{k}`"
        label = re.split(r" \(|（", t(f"param.{k}"))[0]  # the label without its parenthesised note
        return f"{label} (`{k}`)" if lang() != "zh-TW" else f"{label}（`{k}`）"
    return t("common.list").join(one(k) for k in keys)


HASH_ROWS = {"data_in": 9, "data_out": 4, "model_in": 6, "model_out": 3}  # rows of each table on the hash page (texts: hp.<table>.<row>.<0|1>)


def hash_rows(table, **values):
    """The (parameter, description) rows of one table of the hash page; "@lgbm" / "@mlp" in a text stands for the option names."""
    names = {"@lgbm": _option_names(fingerprint.LGBM_OPTIONS), "@mlp": _option_names(fingerprint.MLP_OPTIONS) + t("hp.mlp_extra")}
    out = []
    for i in range(HASH_ROWS[table]):
        first, second = t(f"hp.{table}.{i}.0", **values), t(f"hp.{table}.{i}.1", **values)
        out.append((first, names.get(second, second)))
    return out


def hash_page():
    rev, now = fingerprint.current_rules_revision(), fingerprint.rules_name(fingerprint.current_rules_revision())
    values = {"now": now, "rev": rev, "fmt": fingerprint.HASH_FORMAT}
    with card("hash-what", t("hp.what.card")):
        st.markdown(t("hp.what.body"))
        st.caption(t("hp.what.note"))
    with card("hash-data", t("hp.data.card")):
        st.markdown(t("hp.in"))
        st.table(pd.DataFrame(hash_rows("data_in", **values), columns=[t("hp.col.param"), t("hp.col.desc")]).set_index(t("hp.col.param")))
        st.markdown(t("hp.out"))
        st.table(pd.DataFrame(hash_rows("data_out"), columns=[t("hp.col.param"), t("hp.col.reason")]).set_index(t("hp.col.param")))
    with card("hash-model", t("hp.model.card")):
        st.markdown(t("hp.in"))
        st.table(pd.DataFrame(hash_rows("model_in"), columns=[t("hp.col.param"), t("hp.col.desc")]).set_index(t("hp.col.param")))
        st.markdown(t("hp.out"))
        st.table(pd.DataFrame(hash_rows("model_out"), columns=[t("hp.col.param"), t("hp.col.reason")]).set_index(t("hp.col.param")))
        st.caption(t("hp.model.note"))
    with card("hash-match", t("hp.match.card")):
        st.markdown(t("hp.match.body"))
    with card("hash-versions", t("hp.versions.card")):
        st.markdown(t("hp.versions.body", now=now))
    with card("hash-use", t("hp.use.card")):
        st.markdown(t("hp.use.body", now=now))
    with card("hash-look", t("hp.look.card")):
        dumps = [d for d in list_dumps() if "_fp" in d]
        choices = {t("hp.look.data", name=d["來源"]): (d["_recipe"], d["_fp"]) for d in dumps}
        for mp in model_files():
            meta = model_meta(mp)
            if meta and meta.get("recipe"):
                choices[t("hp.look.model", name=os.path.basename(mp))] = (meta["recipe"], meta["fingerprint"])
        if not choices:
            st.caption(t("hp.look.none"))
            return
        pick = st.selectbox(t("hp.look.pick"), list(choices), key="hash-look-pick")
        recipe, full = choices[pick]
        st.markdown(t("hp.look.hash", hash=full))
        st.json(recipe, expanded=2)


def _esc(text):
    import html
    return html.escape(str(text))


def loss_chart(values, steps=None, height=240):
    """The validation-loss curve as a fixed chart: no zoom or pan, both axes fixed to the data plus a margin on every side (so the line
    never touches the frame), whole steps on the x axis."""
    steps = list(steps) if steps is not None else list(range(1, len(values) + 1))
    step, loss = t("md.step"), t("md.valid_loss")
    df = pd.DataFrame({step: steps, loss: list(values)})
    lo, hi = float(df[loss].min()), float(df[loss].max())
    ypad = (hi - lo) * 0.12 or max(abs(hi) * 0.02, 0.001)
    first, last = float(min(steps)), float(max(steps))
    xpad = max(0.5, (last - first) * 0.04)
    chart = alt.Chart(df).mark_line(color="#4aa8ff", strokeWidth=2, point=alt.OverlayMarkDef(color="#4aa8ff", size=18)).encode(
        x=alt.X(f"{step}:Q", scale=alt.Scale(domain=[first - xpad, last + xpad], nice=False), axis=alt.Axis(tickMinStep=1, format="d", title=step)),
        y=alt.Y(f"{loss}:Q", scale=alt.Scale(domain=[lo - ypad, hi + ypad], nice=False, zero=False), axis=alt.Axis(title=loss, format=".3f")),
        tooltip=[alt.Tooltip(f"{step}:Q", format="d"), alt.Tooltip(f"{loss}:Q", format=".4f")])
    return chart.properties(height=height, padding={"left": 12, "right": 18, "top": 14, "bottom": 10})


def version_tiles(items, centre=False):
    """Tiles like the Dashboard's (label small and muted at the top left, value centred): [(label, value)] or
    [(label, value, help)]; a help text puts a "?" at the top right that shows it on hover.
    centre=True: the value is centred in the whole tile (vertically too), not just in the space under the label."""
    def tile(item):
        label, value, tip = (tuple(item) + (None,))[:3]
        q = f'<span class="q" title="{_esc(tip)}">?</span>' if tip else ""
        return f'<div class="vtile"><div class="l">{_esc(label)}</div>{q}<div class="v">{_esc(value)}</div></div>'
    return f'<div class="vtiles{" mid" if centre else ""}">' + "".join(tile(i) for i in items) + "</div>"


METRIC_HELP = {"R²": t("md.help.r2"), "交叉熵": t("md.help.ce")}


def version_table(head, rows, css=""):
    """A table like the Dashboard's version tables: centred headings; rows are lists of (text, kind) with kind
    'c' = centred, 'l' = left, 'list' = a bullet list (text is a list), 'code' = centred code."""
    def cell(value, kind):
        if kind == "list":
            return '<td class="l"><ul>' + "".join(f"<li>{_esc(x)}</li>" for x in value) + "</ul></td>"
        if kind == "code":
            return f'<td class="c"><code>{_esc(value)}</code></td>'
        return f'<td class="{kind}">{_esc(value)}</td>'
    return (f'<table class="vtable {css}"><thead><tr>' + "".join(f"<th>{_esc(h)}</th>" for h in head) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(cell(v, k) for v, k in r) + "</tr>" for r in rows) + "</tbody></table>")


def versions_page():
    tracks, error = fingerprint.load_versions()
    if error:
        st.error(error)
        return
    with card("ver-now", t("ver.now")):
        st.markdown(version_tiles([(t("ver.rules"), fingerprint.rules_name(fingerprint.current_rules_revision())),
                                   (t("ver.engine"), fingerprint.current_engine_version()),
                                   (t("ver.features"), fingerprint.current_feature_version()),
                                   (t("ver.format"), fingerprint.current_format_version())]), unsafe_allow_html=True)
        now = {"rules": str(fingerprint.current_rules_revision()), "engine": fingerprint.current_engine_version(),
               "features": str(fingerprint.current_feature_version()), "format": str(fingerprint.current_format_version())}
        stale = [k["title"] for k in tracks.values() if k["id"] in now and (k["entries"] or [{}])[0].get("version") != now[k["id"]]]
        if stale:
            st.warning(t("ver.stale", names=", ".join(stale)))
        st.caption(t("ver.caption"))
    for track in tracks.values():
        entries = track.get("entries", [])
        cur = entries[0]["version"] if entries else "?"
        show = lambda v, track=track: track["display"].replace("{version}", str(v))  # noqa: E731
        with card(f"ver-{track['id']}", track["title"]):
            st.markdown(f"<div class='vnote'><b>{t('ver.current', v=_esc(show(cur)))}</b> · {t('ver.source')}: <code>{_esc(track['source'])}</code></div>"
                        f"<div class='vnote'>{_esc(track['meaning'])}</div><div class='vnote'><b>{t('ver.bump')}: </b>{_esc(track['bump'])}</div>"
                        + version_table([t("ver.col.version"), t("ver.col.date"), "commit", t("ver.col.changes")],
                                        [[(show(e["version"]), "c"), (e["date"], "c"), ((e.get("commit") or "")[:8] or "—", "code"),
                                          (e["changes"], "list")] for e in entries]), unsafe_allow_html=True)
    (info, strategies), _ = fingerprint.load_versions(strategies=True)
    with card("ver-strategies", info.get("title", t("ver.strategies"))):
        rows, mismatch = [], []
        for strat in strategies:
            e = (strat.get("entries") or [{}])[0]
            code = fingerprint.current_strategy_revision(strat["id"])
            if code is not None and str(code) != str(e.get("version")):
                mismatch.append(strat["id"])
            rows.append([(strat["id"], "l nw"), (fingerprint.strategy_name(strat["id"], e.get("version", "?")), "c"),
                         (f"v{code}" if code is not None else "—", "c"), (e.get("date", ""), "c"),
                         ((e.get("commit") or "")[:8] or "—", "code"), (e.get("changes", []), "list")])
        if mismatch:
            st.warning(t("ver.strategy_mismatch", names=", ".join(mismatch)))
        st.markdown(f"<div class='vnote'>{_esc(info.get('meaning', ''))}</div><div class='vnote'><b>{t('ver.bump')}: </b>{_esc(info.get('bump', ''))}</div>"
                    + version_table([t("ver.col.strategy"), t("ver.col.current"), t("ver.col.code"), t("ver.col.date"), "commit", t("ver.col.this")], rows), unsafe_allow_html=True)
        with st.expander(t("ver.history")):
            st.markdown(version_table([t("ver.col.version"), t("ver.col.date"), "commit", t("ver.col.changes")],
                                      [[(fingerprint.strategy_name(strat["id"], e["version"]), "c"), (e["date"], "c"),
                                        ((e.get("commit") or "")[:8] or "—", "code"), (e["changes"], "list")]
                                       for strat in strategies for e in strat.get("entries", [])]), unsafe_allow_html=True)


# left navigation like the Dashboard: (id, title, icon, page function, section heading shown above it)
# ---------------------------------------------------------------- 管線（產生資料 → 訓練 → 對戰，整條一起排隊）
# Data sets, models to train and matches are items (dicts in the session state: "pl-data", "pl-train", "pl-match"). An item is set up in a
# dialog; the page shows it read-only, like the summary of an order. To change one, remove it and add it again.

PIPELINES_DIR = os.path.join(LOCAL_DIR, "pipelines")
FEATURE_COUNTS = {1: 430, 2: 512}   # features per feature version (the training page shows the real count of the data it is given)
ROWS_PER_GAME = {4: 2240, 3: 1600}  # rows a game gives per unit of sampling rate (about: decisions x seats); only for the estimates
PL_TRANSIENT = ("pl-store", "pl-tpl-pick", "pl-tpl-name", "pl-tpl-error", "pl-inline")


def pl_inline():
    """Tests only (PR_UI_INLINE_DIALOGS): AppTest cannot rerun a dialog on its own, so the form is drawn in the page instead."""
    return bool(os.environ.get("PR_UI_INLINE_DIALOGS"))


def pl_savable(key, value):
    """The settings of the pipeline form: what is kept between page visits and saved in a template."""
    return (key.startswith("pl-") and key not in PL_TRANSIENT and not key.startswith(("pl-btn", "pl-tpl"))
            and isinstance(value, (str, int, float, bool, list)))


def pl_restore():
    """Streamlit forgets the value of a widget that was not drawn (another page was open): put back what the form had."""
    for k, v in st.session_state.get("pl-store", {}).items():
        if k not in st.session_state:
            st.session_state[k] = v


def pl_persist():
    st.session_state["pl-store"] = {k: v for k, v in st.session_state.items() if pl_savable(k, v)}


def pl_default(key, token, value):
    """Puts `value` in the widget `key` the first time and whenever `token` changes; otherwise the widget keeps what was typed. (A default
    that is passed as `value=` and changes -- a time stamp, the chosen config -- makes a new widget and loses the typed text.)"""
    mark = key + "-for"
    if key not in st.session_state:   # Streamlit drops the state of a widget that was not drawn in a run (another strategy of the seat): the mark outlives it
        st.session_state[key] = value
        st.session_state[mark] = str(token)
    elif st.session_state.get(mark) != str(token):
        if mark not in st.session_state and key in st.session_state:
            st.session_state[mark] = str(token)   # a value that came with no mark: it is the user's, keep it
            return
        st.session_state[key] = value
        st.session_state[mark] = str(token)


def pl_number(label, key, default, token, **kwargs):
    pl_default(key, token, default)
    return st.number_input(label, key=key, **kwargs)


def pl_text(label, key, default, token):
    pl_default(key, token, default)
    return st.text_input(label, key=key).strip()


def pl_select(label, options, key, default=None, **kwargs):
    """selectbox that forgets a remembered value that is no longer among the options (a file was deleted since) and starts on `default`
    (set in the session state, not with index=, so a restored value does not make Streamlit warn)."""
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)
    if key not in st.session_state and default is not None:
        st.session_state[key] = default
    return st.selectbox(label, options, key=key, **kwargs)


def pl_rows(games, rate, players):
    return int(games * rate * ROWS_PER_GAME.get(players, 2000))


# ---- items

def pl_items(kind):
    """The items of a list: "d" data, "t" models to train, "m" matches."""
    return st.session_state.setdefault(pipeline_form.LISTS[kind], [])


def _pl_set_lists(data, train, match):
    st.session_state["pl-data"], st.session_state["pl-train"], st.session_state["pl-match"] = data, train, match
    pl_persist()


def pl_item_add(kind, item):
    pl_items(kind).append(item)
    pl_persist()


def pl_item_remove(kind, i):
    _pl_set_lists(*pipeline_form.remove_item(pl_items("d"), pl_items("t"), pl_items("m"), kind, i))


def pl_items_clear(kind):
    _pl_set_lists(*pipeline_form.clear_items(pl_items("d"), pl_items("t"), pl_items("m"), kind))


def pl_new_players():
    """Items are made for one player count: another count starts a new form."""
    _pl_set_lists([], [], [])


# ---- templates

def pl_saved_templates():
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(PIPELINES_DIR, "*.json")))


def pl_save_template():
    name = (st.session_state.get("pl-tpl-name") or "").strip()
    if not safe_name(name):
        st.session_state["pl-tpl-error"] = t("pl.tpl.bad_name")
        return
    settings = {k: v for k, v in st.session_state.items() if pl_savable(k, v)}
    write_config(os.path.join(PIPELINES_DIR, name + ".json"), {"schemaVersion": 3, "name": name, "settings": settings})
    st.session_state["pl-tpl-error"] = None
    st.session_state["job-started"] = t("pl.tpl.saved", name=name)


def pl_load_template():
    name = st.session_state.get("pl-tpl-pick")
    data = read_config(os.path.join(PIPELINES_DIR, f"{name}.json")) if name else None
    if not data or not isinstance(data.get("settings"), dict):
        return
    settings = pipeline_form.items_from_widget_settings(data["settings"])  # the first pages' templates (one key per row) become item lists
    for k in [k for k, v in st.session_state.items() if pl_savable(k, v)]:
        st.session_state.pop(k, None)                          # the form is replaced, not mixed with what was there
    for k, v in settings.items():
        if pl_savable(k, v):
            st.session_state[k] = v   # before the widgets are drawn (this runs first on the next rerun)
    pl_persist()
    st.session_state["job-started"] = t("pl.tpl.loaded", name=name)


def pl_template_card():
    with card("pl-template", t("pl.tpl.card"), t("pl.tpl.sub")):
        saved = pl_saved_templates()
        c1, c2, c3 = st.columns([3, 1.2, 2], vertical_alignment="bottom")
        with c1:
            pick = pl_select(t("pl.tpl.pick"), saved if saved else [t("pl.tpl.none")], "pl-tpl-pick", disabled=not saved)
        c2.button(t("pl.tpl.load"), key="pl-btn-load", disabled=not saved, on_click=pl_load_template, width="stretch")
        with c3:
            if saved:
                delete_button("del-pl-tpl", t("pl.tpl.delete"), [os.path.join(PIPELINES_DIR, f"{pick}.json")])
        d1, d2 = st.columns([3, 1.2], vertical_alignment="bottom")
        d1.text_input(t("pl.tpl.name"), key="pl-tpl-name")
        d2.button(t("pl.tpl.save"), key="pl-btn-save", on_click=pl_save_template, width="stretch")
        if st.session_state.get("pl-tpl-error"):
            st.markdown(f'<span class="act-err">{plain(st.session_state["pl-tpl-error"])}</span>', unsafe_allow_html=True)


# ---- what an item will do (plans: no widgets, so the page and the dialogs use the same checks)

SEAT_ORDERS = ("random", "balanced", "rotate", "fixed")   # same as the Dashboard


def pl_known_dumps(players):
    return {d["path"]: d for d in list_dumps() if "error" not in d and not d.get("writing") and d["人數"] == players}


def pl_data_plan(item, players, others):
    """What a data item will produce: files, estimates, the job; `problems` says what blocks it. A plan without "out_rel" is unusable."""
    mode = item.get("mode", "config")
    plan = {"item": item, "mode": mode, "problems": [], "details": []}
    problems = plan["problems"]
    name = str(item.get("name", "")).strip()
    games, seed = int(item.get("games") or 0), int(item.get("seed") or 0)
    rate, feature, threads = float(item.get("rate") or 0), int(item.get("feature") or 0), int(item.get("threads") or 0)
    seat_order = item.get("seat_order") if item.get("seat_order") in SEAT_ORDERS else "random"
    if mode == "config":
        config = item.get("config") or ""
        cfg = read_config(absolute(config)) if config else None
        if not cfg or cfg.get("players") != players:
            problems.append(t("pl.data.p.config", name=os.path.basename(config) or "?"))
            return plan
        eff = {**cfg, "games": games, "seed": seed}
        plan.update(config=config, title_key="job.title.dump_config", title_args={})
        source = [(t("pl.det.source"), t("pl.data.mode.config"), 1, 1, 1), (t("pl.det.config"), os.path.basename(config), 1, 2, 3)]
    elif mode == "custom":
        seats = item.get("seats") or []
        names = all_strategies()
        problems += [s_["error"] for s_ in seats if s_.get("error")]
        if len(seats) != players or any(s_.get("strategy") not in names for s_ in seats):
            problems.append(t("pl.data.p.seats"))
            return plan
        for s_ in seats:
            vm = (s_.get("params") or {}).get("valueModel")
            if vm and not os.path.exists(absolute(vm)):
                problems.append(t("pl.data.p.model", name=os.path.basename(vm)))
                return plan
        eff = {"schemaVersion": 1, "name": name, "players": players, "games": games, "seed": seed, "seatOrder": seat_order,
               "seats": [{"id": f"{s_['strategy']}-{i}", "strategy": s_["strategy"], "params": dict(s_.get("params") or {})} for i, s_ in enumerate(seats)],
               "output": {"perGameRecords": False}}
        strategies = t("common.list").join(s_["strategy"] for s_ in seats)
        plan.update(title_key="job.title.dump_custom", title_args={"strategies": strategies})
        source = [(t("pl.det.source"), t("pl.data.mode.custom"), 1, 1, 1), (t("pl.det.seats"), "\n".join(
            f"{i + 1}. {s_['strategy']}" + (f" ({', '.join(f'{k}={v}' for k, v in (s_.get('params') or {}).items())})" if s_.get("params") else "")
            for i, s_ in enumerate(seats)), 1, 2, 5)]
    else:
        model = item.get("model") or ""
        if not model or not os.path.exists(model_path(model)):
            problems.append(t("pl.data.p.model", name=model or "?"))
            return plan
        sims, leaf = int(item.get("sims") or 100), int(item.get("leaf") or 0)
        eff = {**selfplay_config(name, players, games, seed, sims, leaf, rel(model_path(model))), "seatOrder": seat_order}
        plan.update(model=model, sims=sims, leaf=leaf, title_key="job.title.dump_selfplay", title_args={"model": model})
        source = [(t("pl.det.source"), t("pl.data.mode.selfplay"), 1, 1, 1), (t("pl.det.model"), model, 1, 2, 3),
                  (t("pl.det.sims"), str(sims), 1, 5, 1), (t("pl.det.leaf"), str(leaf), 1, 6, 1)]
    out = os.path.join(jobs.results_dir(), "ml", name + ".bin")
    out_rel = rel(out)
    if not safe_name(name):
        problems.append(t("dt.p.name"))
    elif os.path.exists(out):
        problems.append(t("pl.p.exists", name=name + ".bin"))
    elif name in others:
        problems.append(t("pl.data.p.dup", name=name))
    if safe_name(name) and pending_output(out_rel):
        problems.append(t("dt.p.pending"))
    if mode != "config" and safe_name(name) and any(os.path.exists(os.path.join(d, name + ".json"))
                                                      for d in (os.path.join(ROOT, "ml", "data-configs"), LOCAL_CONFIGS)):
        problems.append(t("dt.p.config_taken", name=name))
    twins = []
    try:
        new_fp = fingerprint.fingerprint(fingerprint.planned_dump_recipe(eff, rate, feature))
        twins = [d["來源"] for d in list_dumps() if d.get("_fp") == new_fp and d["path"] != out_rel]
    except (KeyError, ValueError, TypeError):
        pass
    plan.update(name=name, out=out, out_rel=out_rel, games=games, seed=seed, rate=rate, threads=threads, feature=feature,
                rows=pl_rows(games, rate, players), eff=eff, twins=twins)
    plan["details"] = source + [(t("pl.det.games"), f"{games:,}", 2, 1, 1), (t("pl.det.seed"), str(seed), 2, 2, 1), (t("pl.det.rate"), f"{rate:g}", 2, 3, 1),
                                (t("pl.det.feature"), str(feature), 2, 4, 1), (t("pl.det.output"), name + ".bin", 3, 1, 6)]
    if mode != "config":
        plan["details"].append((t("pl.det.seat_order"), seat_order, 2, 5, 1))
    return plan


def pl_train_defaults(kind):
    return dict(train_lgbm.DEFAULTS if kind == "train_lgbm" else train_mlp.DEFAULTS)


def pl_train_plan(item, players, datas, by_path, others):
    kind = item.get("kind", "train_lgbm")
    ext = ".txt" if kind == "train_lgbm" else ".json"
    name = str(item.get("name", "")).strip()
    plan = {"item": item, "kind": kind, "name": name, "ext": ext, "problems": [], "details": []}
    problems = plan["problems"]
    paths, versions, total, labels = [], set(), 0, []
    for tok in item.get("data", []):
        k = pipeline_form.token_index(tok)
        if k is not None:
            d = datas[k] if k < len(datas) else {}
            if "out_rel" in d:   # a data set with a problem shows it on its own card
                paths.append(d["out_rel"])
                versions.add(d["feature"])
                total += d["rows"]
                labels.append(t("pl.train.new_item", n=k + 1, name=d["name"]))
        elif tok in by_path:
            paths.append(tok)
            versions.add(by_path[tok]["特徵版本"])
            total += by_path[tok]["列數"]
            labels.append(os.path.basename(tok))
        else:
            problems.append(t("pl.train.p.gone", file=os.path.basename(tok)))
    if not paths:
        problems.append(t("pl.train.p.no_data"))
    if len(versions) > 1:
        problems.append(t("pl.train.p.versions", versions=t("common.list").join(str(v) for v in sorted(versions))))
    out = os.path.join(LOCAL_MODELS, name + ext)
    if not safe_name(name):
        problems.append(t("tr.p.name"))
    elif os.path.exists(out) or model_name_taken(name + ext):
        problems.append(t("pl.p.exists", name=name + ext))
    elif name + ext in others:
        problems.append(t("pl.train.p.dup", name=name + ext))
    if safe_name(name) and pending_output(rel(out)):
        problems.append(t("tr.p.pending", name=name + ext))
    options = dict(item.get("options") or {})
    changed = [f"{k}={v:g}" if isinstance(v, float) else f"{k}={v}" for k, v in options.items() if k in pl_train_defaults(kind) and v != pl_train_defaults(kind)[k]]
    memory = None
    if total and len(versions) == 1:
        v = next(iter(versions))
        f = max([by_path[x].get("_features") or 0 for x in item.get("data", []) if x in by_path] + [FEATURE_COUNTS.get(v, 430)])
        memory = (total, f, total * f * 4 * 2.2 / 1e9 if kind == "train_lgbm" else total * f * 2 * 1.5 / 1e9)
    plan.update(out=out, out_rel=rel(out), options=options, paths=paths, rows=total, memory=memory)
    plan["details"] = ([(t("pl.det.name"), name + ext, 1, 1, 3), (t("pl.det.kind"), KIND_TEXT[kind], 1, 4, 1),
                        (t("pl.det.params"), ", ".join(changed) if changed else t("pl.det.params_default"), 1, 5, 2),
                        (t("pl.det.data"), "\n".join(labels) if labels else "—", 2, 1, 6)]
                       + ([(t("pl.det.memory"), t("pl.train.est", rows=f"{memory[0]:,}", f=memory[1], gb=f"{memory[2]:.1f}"), 3, 1, 6)] if memory else []))
    return plan


def pl_match_plan(item, players, trains, others):
    plan = {"item": item, "problems": [], "details": []}
    problems = plan["problems"]
    token = item.get("model")
    k = pipeline_form.token_index(token)
    if k is not None:
        tr = trains[k] if k < len(trains) else {}
        if "out_rel" not in tr:
            problems.append(t("pl.match.p.model_gone"))
            return plan
        model_name, model_rel = tr["name"] + tr["ext"], tr["out_rel"]
    else:
        if not token or not os.path.exists(model_path(token)):
            problems.append(t("pl.match.p.model_missing", name=token or "?"))
            return plan
        model_name, model_rel = token, rel(model_path(token))
    table, rival = item.get("table", "default"), item.get("rival")
    sims, leaf, bsims = int(item.get("sims") or 300), int(item.get("leaf") or 0), int(item.get("bsims") or 300)
    games, seed, threads = int(item.get("games") or 0), int(item.get("seed") or 0), int(item.get("threads") or 0)
    if table == "model" and (not rival or not os.path.exists(model_path(rival))):
        problems.append(t("pl.match.p.rival", name=rival or "?"))
        return plan
    perm = 24 if players == 4 else 6
    if games % perm or games < perm:
        problems.append(t("match.p.games", perm=perm))
    name = match_default_name(model_name, sims, leaf, table, rival, bsims, seed)
    out = os.path.join(jobs.results_dir(), "ml", name + ".json")
    if name in others:
        problems.append(t("pl.match.p.dup", name=name))
    elif os.path.exists(out):
        problems.append(t("pl.p.exists", name=name + ".json"))
    elif pending_output(rel(out)):
        problems.append(t("match.p.pending"))
    plan.update(table=table, rival=rival, sims=sims, leaf=leaf, bsims=bsims, games=games, seed=seed, threads=threads, name=name, out=out, out_rel=rel(out),
                model_name=model_name, model_rel=model_rel, train_index=k,
                seats=match_seats(table, players, model_name, sims, leaf, bsims, rival, model_rel=model_rel))
    opp = rival if table == "model" else t(f"pl.match.opp.{table}")
    plan["details"] = ([(t("pl.det.model"), model_name, 1, 1, 2), (t("pl.det.opponent"), opp, 1, 3, 2),
                        (t("pl.det.sims"), str(sims), 1, 5, 1), (t("pl.det.leaf"), str(leaf), 1, 6, 1),
                        (t("pl.det.games"), f"{games:,}", 2, 1, 1), (t("pl.det.seed"), str(seed), 2, 2, 1)]
                       + ([(t("pl.det.opp_sims"), str(bsims), 2, 3, 1)] if table != "hand" else [])
                       + [(t("pl.det.result"), name + ".json", 3, 1, 6)])
    return plan


def pl_plans(players):
    """The plans of every item on the page: (data, models, matches). A name counts as taken by the items before it."""
    d_items, t_items, m_items = pl_items("d"), pl_items("t"), pl_items("m")
    by_path = pl_known_dumps(players)
    datas = [pl_data_plan(it, players, [d.get("name") for d in d_items[:i]]) for i, it in enumerate(d_items)]
    trains = []
    for i, it in enumerate(t_items):
        earlier = [(x.get("name", "") + (".txt" if x.get("kind", "train_lgbm") == "train_lgbm" else ".json")) for x in t_items[:i]]
        trains.append(pl_train_plan(it, players, datas, by_path, earlier))
    matches = []
    for i, it in enumerate(m_items):
        matches.append(pl_match_plan(it, players, trains, [m.get("name") for m in matches]))
    return datas, trains, matches


# ---- the dialogs (the forms that make an item)

def pl_dialog_reset():
    for k in [k for k in st.session_state if isinstance(k, str) and k.startswith("pld-")]:
        st.session_state.pop(k, None)


def pl_dialog_buttons(kind, item, problems):
    """Problems in red, then Add (locked while there are problems) and Cancel; both close the dialog (a rerun of the page)."""
    # one block that is always there (an empty one keeps its height): the buttons below must not jump when a problem appears or goes away
    text = f'<span class="act-err">{t("common.sep").join(plain(p_) for p_ in problems)}</span>' if problems else "&nbsp;"
    st.markdown(f'<div class="pl-problems">{text}</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button(t("pl.dlg.add"), key="pld-ok", type="primary", disabled=item is None or bool(problems), width="stretch"):
        pl_item_add(kind, item)
        st.session_state.pop("pl-inline", None)
        st.rerun()
    if c2.button(t("pl.dlg.cancel"), key="pld-cancel", width="stretch"):
        st.session_state.pop("pl-inline", None)
        st.rerun()


def pl_custom_defaults(strategy, players, model_rel):
    """The parameters (and defaults) the engine would use for this seat; with a value model on 4 players leafRollout defaults to 40."""
    d = dict(fingerprint.strategy_table().get(strategy, {}).get("params", {}).get(str(players), {}))
    if strategy == "mcts" and model_rel:
        d["valueModel"] = model_rel
        if "leafRollout" in d:
            d["leafRollout"] = fingerprint.DEFAULT_LEAF_ROLLOUT if players == 4 else 0
    return d


def pl_custom_params(defaults, texts):
    """Typed texts -> only the values that differ from the defaults (numbers become numbers). Raises ValueError on a non-number for a numeric parameter."""
    out = {}
    for k, text in texts.items():
        text, d = str(text).strip(), defaults.get(k)
        if isinstance(d, (int, float)) and not isinstance(d, bool):
            try:
                v = float(text)
            except ValueError:
                raise ValueError(f"{k}={text}") from None
            if v != d:
                out[k] = int(v) if v.is_integer() and "." not in text else v
        elif text != ("" if d is None else str(d)):
            out[k] = text
    return out


@st.cache_data(show_spinner=False)
def documented_params(strategy):
    """The parameters the Dashboard's strategy guide lists for a strategy (i18n/dash.en.json, `strat.<id>.p.N.name`): its own parameters; the shared
    tie-break ones (randomTies, tie*) are not among them. Empty when the guide has nothing (then every parameter is offered)."""
    try:
        with open(os.path.join(ROOT, "i18n", "dash.en.json"), encoding="utf-8") as f:
            texts = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ()
    return tuple(v for k, v in texts.items() if re.fullmatch(rf"strat\.{re.escape(strategy)}\.p\.\d+\.name", k))


def strategy_display_name(strategy):
    """The strategy's name as the Dashboard's simulate page shows it (Palette.DisplayName)."""
    if strategy == "mcts":
        return "MCTS"
    if strategy == "random":
        return "Full-Random"
    return "-".join(w[:1].upper() + w[1:] for w in strategy.split("-"))


def strategy_choices():
    """Same list and order as the Dashboard's strategy drop-down: alphabetical, random last."""
    return sorted(all_strategies(), key=lambda n: (n == "random", n))


MCTS_FIRST = ["valueModel", "simulations", "leafRollout", "rolloutRounds", "rolloutStrategy"]   # same order as the Dashboard


def pl_custom_seats(players):
    """The seat rows of the Dashboard's simulate page (seat | strategy | parameters), one framed card per seat; the parameter boxes are filled
    with the defaults and only the strategy's own parameters are offered. Returns the seats (only changed parameters)."""
    names = strategy_choices()
    model_names = [t("custom.model_none")] + [os.path.basename(p_) for p_ in models_for(players)]
    widths = [1, 3.4, 8]
    heads = st.columns(widths)
    for c_, key in zip(heads, ("pl.data.col.seat", "pl.data.col.strategy", "pl.data.col.params")):
        c_.markdown(f'<span class="pl-seathead">{t(key)}</span>', unsafe_allow_html=True)
    seats = []
    for i in range(players):
        default = DEFAULT_CUSTOM[players][i] if DEFAULT_CUSTOM[players][i] in names else names[0]
        pl_default(f"pld-cs{i}", f"players|{players}", default)
        pl_default(f"pld-cm{i}", f"players|{players}", model_names[0])
        if st.session_state.get(f"pld-cm{i}") not in model_names:
            st.session_state[f"pld-cm{i}"] = model_names[0]
        with st.container(border=True, key=f"pl-seatcard-{i}"):
            c1, c2, c3 = st.columns(widths, vertical_alignment="center")
            c1.markdown(f"**{t('custom.seat', n=i + 1)}**")
            strat = c2.selectbox(t("custom.seat", n=i + 1), names, key=f"pld-cs{i}", label_visibility="collapsed", format_func=strategy_display_name)
            model_choice = st.session_state[f"pld-cm{i}"]
            model_rel = rel(model_path(model_choice)) if strat == "mcts" and model_choice != model_names[0] else ""
            defaults = pl_custom_defaults(strat, players, model_rel)
            documented = documented_params(strat)
            keys = [k for k in defaults if not documented or k in documented]
            if strat == "mcts":
                keys = [k for k in MCTS_FIRST if k in keys] + [k for k in keys if k not in MCTS_FIRST]
            texts = {}
            with c3:
                if not keys:
                    st.caption(t("pl.data.no_params"))
                for row in range(0, len(keys), 5):
                    cols = st.columns(5)
                    for col, k in zip(cols, keys[row:row + 5]):
                        with col:
                            if k == "valueModel":
                                st.selectbox(t("custom.model"), model_names, key=f"pld-cm{i}")
                                continue
                            key = f"pld-cp{i}-{strat}-{k}"
                            d = defaults[k]
                            pl_default(key, f"{players}|{strat}|{model_rel}", "" if d is None else f"{d:g}" if isinstance(d, float) else str(d))
                            if k == "rolloutStrategy":
                                choices = [n for n in names if n != "mcts"]
                                if st.session_state.get(key) not in choices:
                                    st.session_state[key] = d if d in choices else choices[0]
                                st.selectbox(k, choices, key=key, format_func=strategy_display_name)
                            else:
                                st.text_input(k, key=key)
                            texts[k] = st.session_state[key]
        seat = {"strategy": strat}
        try:
            params = pl_custom_params({k: defaults[k] for k in texts}, texts)
        except ValueError as e:
            params, seat["error"] = {}, t("custom.seat_param_error", n=i + 1, error=e)
        if model_rel:
            params["valueModel"] = model_rel
            params["leafRollout"] = int(float(texts.get("leafRollout", defaults.get("leafRollout", 0))) if "error" not in seat else 0)   # also 0: the default is 40 with a model
        seat["params"] = params
        seats.append(seat)
    return seats


def pl_data_form(players, count):
    """The settings of a new data set (inside the dialog); returns the item, or None when there is nothing to choose from."""
    pl_default("pld-mode", "open", "config")   # set (not just popped by the reset) so the radio really goes back to the first choice
    mode = st.radio(t("pl.data.mode"), ["config", "custom", "selfplay"], format_func=lambda m: t(f"pl.data.mode.{m}"), horizontal=True, key="pld-mode")
    item = {"mode": mode}
    stamp = datetime.datetime.now().strftime("%m%d-%H%M")
    suffix = f"-{count + 1}" if count else ""   # a second data set from the same config or model must not start with the same name
    if mode == "config":
        rows = [r for r in config_rows() if r["人數"] == players]
        if not rows:
            st.info(t("pl.data.no_config", n=players))
            return None
        by_name = {r["設定檔"]: r for r in rows}
        config = pl_select(t("dt.which_config"), list(by_name), "pld-config",
                           format_func=lambda c: t("dt.config_item", file=os.path.basename(c), players=by_name[c]["人數"], seats=by_name[c]["座位"]))
        cfg = read_config(absolute(config)) or {}
        games_d, seed_d = int(cfg.get("games", 20000)), int(cfg.get("seed", 1))
        rate_d = float((cfg.get("output") or {}).get("dumpRate") or (0.05 if any(s_.get("strategy") == "mcts" for s_ in cfg.get("seats", [])) else 0.01))
        name_d, token = os.path.basename(config)[:-5] + suffix, config
        item["config"] = config
    elif mode == "custom":
        seats = pl_custom_seats(players)
        has_mcts = any(s_["strategy"] == "mcts" for s_ in seats)
        games_d, seed_d, rate_d = (2000 if has_mcts else 20000), int(datetime.datetime.now().strftime("%m%d%H")) + count, (0.05 if has_mcts else 0.01)
        name_d, token = f"{players}p-custom-{stamp}{suffix}", "|".join(s_["strategy"] for s_ in seats)
        item["seats"] = seats
        if has_mcts:
            st.caption(t("dt.mcts_slow"))
    else:
        cands = [os.path.basename(p_) for p_ in models_for(players)]
        if not cands:
            st.info(t("dt.no_model", n=players))
            return None
        model = pl_select(t("dt.which_model"), cands, "pld-model", default=cands[-1])
        c1, c2 = st.columns(2)
        with c1:
            sims = pl_number(t("dt.sp_sims"), "pld-sims", 100, "sims", min_value=1, step=50, help=t("dt.sp_sims_help"))
        with c2:
            leaf = pl_number(t("dt.sp_leaf"), "pld-leaf", 20, "leaf", min_value=0, step=5)
        games_d, seed_d, rate_d = 4000, int(datetime.datetime.now().strftime("%m%d%H")) + count, 0.05
        name_d, token = f"{players}p-selfplay-{model.rsplit('.', 1)[0].replace(f'{players}p-', '')}-{stamp}{suffix}", model
        item.update(model=model, sims=int(sims), leaf=int(leaf))
    token = f"{mode}|{players}|{token}"
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        games = pl_number(t("dt.games"), "pld-games", games_d, token, min_value=1, step=1000)
    with c2:
        seed = pl_number(t("dt.seed"), "pld-seed", seed_d, token, step=1)
    with c3:
        rate = pl_number(t("dt.rate"), "pld-rate", rate_d, token, min_value=0.0001, max_value=1.0, format="%g")
    with c4:
        threads = pl_number(t("dt.threads"), "pld-threads", 0, "threads", min_value=0, step=1)
    versions = fingerprint.feature_versions()
    known = [d["特徵版本"] for d in pl_known_dumps(players).values()]
    common = max(set(known), key=known.count) if known else None
    with c5:
        pl_default("pld-feature", f"feature|{players}", common if common in versions else versions[-1])
        feature = pl_select(t("dt.feature"), versions, "pld-feature", help=t("dt.feature_help"))
    if common is not None and feature != common:
        st.caption(t("pl.data.feature_note", v=common))
    if mode == "config":
        name = pl_text(t("dt.name"), "pld-name", name_d, token)
    else:   # the seat order of a new combination (a config file has its own)
        n1, n2 = st.columns([3, 2])
        with n1:
            name = pl_text(t("dt.name"), "pld-name", name_d, token)
        with n2:
            item["seat_order"] = pl_select(t("pl.data.seat_order"), list(SEAT_ORDERS), "pld-seatorder", default="random", format_func=lambda o: t(f"pl.data.so.{o}"))
    item.update(games=int(games), seed=int(seed), rate=float(rate), threads=int(threads), feature=int(feature), name=name)
    return item


def pl_data_dialog(players):
    count = len(pl_items("d"))
    item = pl_data_form(players, count)
    plan = pl_data_plan(item, players, [d.get("name") for d in pl_items("d")]) if item else {"problems": []}
    if plan.get("twins"):
        st.info(t("dt.twins", list=t("common.list").join(f"`{n_}`" for n_ in plan["twins"])))
    pl_dialog_buttons("d", item, plan["problems"])


def pl_train_dialog(players):
    datas, trains, _ = pl_plans(players)
    by_path = pl_known_dumps(players)
    new_tokens = [pipeline_form.new_token(k) for k, d in enumerate(datas) if "out_rel" in d]
    options = new_tokens + list(by_path)
    pl_default("pld-data", "init", list(new_tokens))   # a new model starts with the data sets of this pipeline
    chosen_before = [x for x in (st.session_state.get("pld-data") or []) if x in options]
    current_rules = fingerprint.rules_name(fingerprint.current_rules_revision())

    def seat_text(seats):  # an MCTS seat names the value model it plays with, as in the data tables
        names = []
        for x in seats or []:
            vm = (x.get("params") or {}).get("valueModel")
            names.append(f"{x['strategy']}({os.path.splitext(os.path.basename(str(vm)))[0]})" if vm and x.get("strategy") else x.get("strategy"))
        return t("common.list").join(dict.fromkeys(n for n in names if n))

    def data_row(tok):
        k = pipeline_form.token_index(tok)
        if k is not None:
            d = datas[k]
            try:
                new_hash = fingerprint.short(fingerprint.fingerprint(fingerprint.planned_dump_recipe(d["eff"], d["rate"], d["feature"])))
            except (KeyError, ValueError, TypeError):
                new_hash = "—"
            return {"kind": t("pl.train.kind_new", n=k + 1), "file": d["name"] + ".bin", "players": players, "games": d["games"], "rows": d["rows"],
                    "rate": d["rate"], "feature": d["feature"], "size": "—", "strategies": seat_text(d["eff"].get("seats")), "hash": new_hash,
                    "rules": current_rules, "commit": "—"}
        d = by_path[tok]
        return {"kind": t("pl.train.kind_existing"), "file": os.path.basename(tok), "players": d["人數"], "games": d["局數"], "rows": d["列數"],
                "rate": d.get("抽樣率"), "feature": d["特徵版本"], "size": d.get("大小 MB", "—"), "strategies": d.get("策略", ""),
                "hash": d.get("hash") or "—", "rules": d.get("規則版本"), "commit": d.get("引擎 commit", "—")}

    all_rows = {tok: data_row(tok) for tok in options}
    if not options:
        st.caption(t("pl.train.no_data_rows"))
    else:
        st.markdown(f"**{t('pl.train.data')}**")
        with st.container(key="filterbar-pl-train"):   # quick filters, same look as the training page's
            f1, f2, f3, _ = st.columns([1, 1, 1, 2])
            kind_opts = [t("pl.train.kind_new_short"), t("pl.train.kind_existing")]
            feature_opts = sorted({r["feature"] for r in all_rows.values()})
            rules_opts = sorted({r["rules"] for r in all_rows.values() if r["rules"]})
            fk = f1.pills(t("pl.train.col.kind"), kind_opts, selection_mode="multi", key="pld-tf-kind")
            fv = f2.pills(t("dump.col.feature"), feature_opts, selection_mode="multi", key="pld-tf-feature")
            rv = f3.pills(t("dump.col.rules"), rules_opts, selection_mode="multi", key="pld-tf-rules")

        def shown(tok):
            r = all_rows[tok]
            is_new = pipeline_form.token_index(tok) is not None
            return ((not fk or kind_opts[0 if is_new else 1] in fk) and r["feature"] in (fv or feature_opts)
                    and (r["rules"] in (rv or rules_opts) or not r["rules"]))

        visible = [tok for tok in options if shown(tok)]
        if not visible:
            st.caption(t("mlist.none"))
        else:
            col = lambda key: t(f"dump.col.{key}")  # noqa: E731
            pick = lambda key, fn=lambda v: v: [fn(all_rows[x][key]) for x in visible]  # noqa: E731
            # the same columns, in the same order, as the training page's data table (plus what kind of data it is)
            frame = pd.DataFrame({t("pl.train.col.kind"): pick("kind"), col("file"): pick("file"), col("players"): pick("players", str),
                                  col("games"): pick("games"), col("rows"): pick("rows"), col("rate"): pick("rate"), col("feature"): pick("feature", str),
                                  col("size"): pick("size", str), col("strategies"): pick("strategies"), "hash": pick("hash"),
                                  col("rules"): pick("rules", lambda v: v or "—"), col("commit"): pick("commit")})
            # a selection is by row number: the filters are part of the key (another filter = another table), and a new table starts with what was chosen
            tkey = f"pld-dtable-{'.'.join(map(str, fk or []))}-{'.'.join(map(str, fv or []))}-{'.'.join(map(str, rv or []))}"
            if tkey not in st.session_state:
                st.session_state[tkey] = {"selection": {"rows": [n for n, x in enumerate(visible) if x in chosen_before], "columns": []}}
            event = grid(frame, hide_index=True, on_select="rerun", selection_mode="multi-row", width="stretch", key=tkey,
                         column_config=dump_column_config())
            selected = {visible[n] for n in event.selection.rows if n < len(visible)}
            hidden_kept = {x for x in chosen_before if x not in visible}    # chosen earlier, hidden by a filter now: still chosen
            st.session_state["pld-data"] = [x for x in options if x in selected or x in hidden_kept]
    chosen_now = [x for x in st.session_state.get("pld-data", []) if x in options]
    rows_now = sum(all_rows[x]["rows"] or 0 for x in chosen_now) if options else 0
    if options:
        st.caption(t("pl.train.chosen", n=len(chosen_now), new=sum(1 for x in chosen_now if pipeline_form.token_index(x) is not None), rows=f"{rows_now:,}")
                   if chosen_now else t("pl.train.chosen_none"))
    picked = [x for x in st.session_state.get("pld-data", []) if x in options]
    pl_default("pld-kind", "open", "train_lgbm")
    kind = st.radio(t("tr.model"), ["train_lgbm", "train_mlp"], format_func=lambda k: KIND_TEXT[k], horizontal=True, key="pld-kind")
    with st.expander(t("pl.train.advanced")):
        opts = param_inputs(pl_train_defaults(kind), f"pld-opt-{kind}", container_key=f"params-pld-{kind}")
    stamp = datetime.datetime.now().strftime("%m%d-%H%M")
    suffix = f"-{len(trains) + 1}" if trains else ""
    players_text = f"{players}p-{'lgbm' if kind == 'train_lgbm' else 'mlp'}-{stamp}{suffix}"
    name = pl_text(t("pl.train.name"), "pld-name", players_text, f"{players}|{kind}")
    item = {"data": picked, "kind": kind, "name": name, "options": opts}
    earlier = [x["name"] + x["ext"] for x in trains]
    plan = pl_train_plan(item, players, datas, by_path, earlier)
    if plan.get("memory"):
        total, f, gb = plan["memory"]
        st.caption(t("pl.train.est", rows=f"{total:,}", f=f, gb=f"{gb:.1f}"))
    pl_dialog_buttons("t", item, plan["problems"])


def pl_match_dialog(players):
    datas, trains, matches = pl_plans(players)
    existing = [os.path.basename(p_) for p_ in models_for(players)]
    trained = [pipeline_form.new_token(k) for k, tr in enumerate(trains) if "out_rel" in tr]
    options = trained + existing
    if not options:
        st.info(t("match.no_model", n=players))
        pl_dialog_buttons("m", None, [])
        return

    def model_label(tok):
        k = pipeline_form.token_index(tok)
        return t("pl.match.model_new", n=k + 1, name=trains[k]["name"] + trains[k]["ext"]) if k is not None else tok

    perm = 24 if players == 4 else 6
    token = pl_select(t("pl.match.model"), options, "pld-model", default=options[0] if trained else options[-1], format_func=model_label)
    k = pipeline_form.token_index(token)
    model_name = trains[k]["name"] + trains[k]["ext"] if k is not None else token
    c1, c2 = st.columns([1, 1])
    with c1:
        table = pl_select(t("match.opponent"), list(MATCH_TABLES), "pld-table", default="default", format_func=MATCH_TABLES.get)
    rival = None
    with c2:
        if table == "model":
            others = pl_best_models(players, exclude=(model_name,))
            if others:
                rival = pl_select(t("match.rival"), others, "pld-rival", default=others[0])
            else:
                st.caption(t("match.only_one", n=players))
    c1, c2, c3 = st.columns(3)
    with c1:
        sims = pl_number(t("pl.match.sims"), "pld-sims", 300, "sims", min_value=1, step=10, help=t("pl.match.sims_help"))
    with c2:
        leaf = pl_number(t("pl.match.leaf"), "pld-leaf", 40 if players == 4 else 0, f"leaf{players}", min_value=0, step=5)
    with c3:
        bsims = pl_number(t("match.base_model") if table == "model" else t("match.base_orig"), "pld-bsims", 300, "b", min_value=1, step=10, disabled=table == "hand")
    c1, c2, c3 = st.columns(3)
    with c1:
        games = pl_number(t("match.games", perm=perm), "pld-games", {"default": 240, "model": 960}.get(table, 408), table, min_value=perm, step=perm)
    with c2:
        seed = pl_number(t("match.seed"), "pld-seed", 9191, "seed", step=1)
    with c3:
        threads = pl_number(t("match.threads"), "pld-threads", 0, "threads", min_value=0, step=1)
    item = {"model": token, "table": table, "rival": rival, "sims": int(sims), "leaf": int(leaf), "bsims": int(bsims), "games": int(games),
            "seed": int(seed), "threads": int(threads)}
    plan = pl_match_plan(item, players, trains, [m.get("name") for m in matches])
    pl_dialog_buttons("m", item, plan["problems"])


def pl_best_models(players, exclude=()):
    """Existing models of this player count, the strongest against the original MCTS first."""
    names = [os.path.basename(p_) for p_ in models_for(players)]
    best = lambda n: (best_vs_default(model_meta(model_path(n))) or {}).get("winShare", -1) if model_meta(model_path(n)) else -1  # noqa: E731
    return sorted((n for n in names if n not in exclude), key=best, reverse=True)


def pl_match_standard(rows, players):
    """Adds the standard validation set: `rows` are (model token, table, rival, games); sets that are already there are skipped."""
    have = {tuple(sorted((k, str(v)) for k, v in m.items())) for m in pl_items("m")}
    for model, table, rival, games in rows:
        item = {"model": model, "table": table, "rival": rival, "sims": 300, "leaf": 40 if players == 4 else 0, "bsims": 300, "games": games,
                "seed": 9191, "threads": 0}
        key = tuple(sorted((k, str(v)) for k, v in item.items()))
        if key not in have:
            pl_items("m").append(item)
            have.add(key)
    pl_persist()


# ---- the cards

def pl_item_card(kind, i, title, plan):
    """One item, read-only: its title, the details of its settings (and what blocks it, in red) and a red Remove button."""
    with st.container(border=True, key=f"pl-item-{kind}{i}"):
        h1, h2 = st.columns([8, 1.3], vertical_alignment="center")
        h1.markdown(f"<div class='pl-rowtitle'>{html.escape(title)}</div>", unsafe_allow_html=True)
        h2.button(t("pl.row.remove"), key=f"stop-pl-rm-{kind}{i}", on_click=pl_item_remove, args=(kind, i), width="stretch")  # stop-: red (CSS)
        if plan["details"]:
            cells = "".join(f"<div class='c' style='grid-area:{row} / {col} / span 1 / span {span}'><span class='k'>{html.escape(k)}</span>"
                            f"<span class='v'>{html.escape(v).replace(chr(10), '<br>')}</span></div>" for k, v, row, col, span in plan["details"])
            st.markdown(f"<div class='pl-detail'>{cells}</div>", unsafe_allow_html=True)
        for p_ in plan["problems"]:
            st.markdown(f'<span class="act-err">{plain(p_)}</span>', unsafe_allow_html=True)


def pl_add_card(kind, players, add_label, dialog_title, form, middle=None):
    """The dashed card under a list: add an item (opens the dialog), optionally one more button (callback + args), remove all (red)."""
    n = len(pl_items(kind))
    with st.container(key=f"pl-addbox-{kind}"):
        cols = st.columns([2, 2.4, 1.6] if middle else [2, 1.6], vertical_alignment="center")
        clicked = cols[0].button(add_label, key=f"pl-btn-add-{kind}", on_click=pl_dialog_reset, width="stretch")
        if middle:
            label, callback, args = middle
            cols[1].button(label, key="pl-btn-standard", on_click=callback, args=args, width="stretch")
        cols[-1].button(t("pl.row.clear"), key=f"stop-pl-clear-{kind}", on_click=pl_items_clear, args=(kind,), disabled=not n, width="stretch")  # stop-: red
    if clicked:
        if pl_inline():
            st.session_state["pl-inline"] = kind
        else:
            st.dialog(dialog_title, width="large")(form)(players)   # a dialog: the page behind it is dimmed
    if pl_inline() and st.session_state.get("pl-inline") == kind:
        with st.container(border=True, key=f"pl-inline-{kind}"):
            st.markdown(f"**{dialog_title}**")
            form(players)


def pl_data_card(players, plans):
    with card("pl-data", t("pl.data.card"), t("pl.data.sub")):
        for i, plan in enumerate(plans):
            pl_item_card("d", i, t("pl.data.row", n=i + 1) + (f"・{plan['name']}" if plan.get("name") else ""), plan)
        if not plans:
            st.caption(t("pl.data.empty"))
        pl_add_card("d", players, t("pl.data.add"), t("pl.data.dialog"), pl_data_dialog)


def pl_train_card(players, plans):
    with card("pl-train", t("pl.train.card"), t("pl.train.sub")):
        for i, plan in enumerate(plans):
            pl_item_card("t", i, t("pl.train.row", n=i + 1) + (f"・{plan['name']}{plan['ext']}" if plan.get("name") else ""), plan)
        if not plans:
            st.caption(t("pl.train.empty"))
        pl_add_card("t", players, t("pl.train.add"), t("pl.train.dialog"), pl_train_dialog)


def pl_match_card(players, plans, trains):
    with card("pl-match", t("pl.match.card"), t("pl.match.sub")):
        for i, plan in enumerate(plans):
            pl_item_card("m", i, t("pl.match.row", n=i + 1), plan)
        if not plans:
            st.caption(t("pl.match.empty"))
        existing = [os.path.basename(p_) for p_ in models_for(players)]
        models = [(pipeline_form.new_token(k), tr["name"] + tr["ext"]) for k, tr in enumerate(trains) if "out_rel" in tr]
        if not models and existing:
            models = [(existing[-1], existing[-1])]
        standard = []
        for token, nm in models:
            others = pl_best_models(players, exclude=(nm,))
            standard += [(token, "model", o, 960) for o in others[:2]] + [(token, "default", None, 240), (token, "hand", None, 408)]
        pl_add_card("m", players, t("pl.match.add"), t("pl.match.dialog"), pl_match_dialog, middle=(t("pl.match.standard"), pl_match_standard, (standard, players)))


# ---- the jobs

def pl_steps(players, datas, trains, matches):
    """The jobs of the pipeline in run order, ready for jobs.start_pipeline (writes nothing): all the data, then every model with its own
    matches right after it, then the matches of existing models."""
    steps = []
    for d in datas:
        spec_config = rel(os.path.join(LOCAL_CONFIGS, d["name"] + ".json")) if d["mode"] != "config" else d["config"]
        args = {"name": d["name"], **d["title_args"]}
        steps.append({"kind": "dump", "stage": "data", "title": t(d["title_key"], **args), "titleKey": d["title_key"], "titleArgs": args,
                      "spec": {"config": spec_config, "out": d["out_rel"], "rate": d["rate"], "games": d["games"], "seed": d["seed"],
                               "threads": d["threads"], "featureVersion": d["feature"]}})

    def match_step(row):
        key = f"job.title.match_{row['table']}"
        args = {"model": row["model_name"], "sims": row["sims"], "rival": row["rival"], "name": row["name"]}
        return {"kind": "match", "stage": "match", "title": t(key, **args), "titleKey": key, "titleArgs": args,
                "spec": {"config": rel(os.path.join(LOCAL_MATCHES, row["name"] + ".json")), "out": row["out_rel"], "model": row["model_rel"]}}

    for k, tr in enumerate(trains):
        args = {"kind": KIND_TEXT[tr["kind"]], "name": tr["name"] + tr["ext"]}
        steps.append({"kind": tr["kind"], "stage": "train", "title": t("job.title.pipeline_train", **args), "titleKey": "job.title.pipeline_train",
                      "titleArgs": args, "spec": {"data": tr["paths"], "out": tr["out_rel"], "options": tr["options"]}})
        steps += [match_step(row) for row in matches if row["train_index"] == k]
    steps += [match_step(row) for row in matches if row["train_index"] is None]
    return steps


def pl_write_configs(players, datas, matches):
    """The config files the jobs read (kept with the others: reusable and reproducible)."""
    for d in datas:
        if d["mode"] != "config":
            write_config(os.path.join(LOCAL_CONFIGS, d["name"] + ".json"), d["eff"])
    for row in matches:
        cfg = {"schemaVersion": 1, "name": row["name"], "players": players, "games": row["games"], "seed": row["seed"],
               "seatOrder": "balanced", "seats": row["seats"], "output": {"perGameRecords": False}}
        if row["threads"]:
            cfg["parallelism"] = {"maxDegree": row["threads"]}
        write_config(os.path.join(LOCAL_MATCHES, row["name"] + ".json"), cfg)


def pl_run_card(players, datas, trains, matches):
    with card("pl-run", t("pl.run.card")):
        default_name = (trains[0]["name"] if trains else "") or (datas[0].get("name") if datas else "") or (matches[0].get("model_name") if matches else "") or "pipeline"
        pipe_name = pl_text(t("pl.run.name"), "pl-run-name", default_name, default_name)
        problems = []
        for plan in [*datas, *trains, *matches]:
            for p_ in plan["problems"]:
                if p_ not in problems:
                    problems.append(p_)
        if not pipe_name:
            problems.append(t("pl.run.p.name"))
        complete = all("out_rel" in p_ for p_ in [*datas, *trains, *matches])
        steps = pl_steps(players, datas, trains, matches) if complete else []
        if not problems and not steps:
            problems.append(t("pl.run.empty"))
        if steps:
            stage_text = {"data": t("pl.run.stage.data"), "train": t("pl.run.stage.train"), "match": t("pl.run.stage.match")}
            frame = pd.DataFrame({t("pl.run.col.step"): [f"{i + 1}. {stage_text[s_['stage']]}" for i, s_ in enumerate(steps)],
                                  t("pl.run.col.job"): [job_title({"title": s_["title"], "titleKey": s_["titleKey"], "titleArgs": s_["titleArgs"]}) for s_ in steps],
                                  t("pl.run.col.output"): [os.path.basename(s_["spec"]["out"]) for s_ in steps]})
            grid(frame, hide_index=True, width="stretch")
            games = sum(r["games"] for r in matches)
            hours = sum(d["games"] for d in datas if d["mode"] == "selfplay") / 3600
            st.caption(t("pl.run.summary", n=len(steps), lo=f"{games * 0.6 / 60:.0f}", hi=f"{games * 1.2 / 60:.0f}")
                       + (t("pl.run.summary_sp", hours=f"{hours:.1f}") if hours else ""))
        if action_row(t("pl.run.start"), "pl-btn-start", problems):
            try:
                pl_write_configs(players, datas, matches)
                ids = jobs.start_pipeline(pipe_name, steps)
            except (OSError, ValueError, TimeoutError) as e:
                st.error(str(e))
            else:
                st.session_state["job-select"] = ids[0]
                st.session_state["job-started"] = t("pl.run.started", name=pipe_name, n=len(ids))
                st.rerun()


def pipeline_page():
    pl_restore()
    st.caption(t("pl.intro"))
    players = st.radio(t("match.players"), [4, 3], horizontal=True, format_func=lambda n: t("match.players_n", n=n), key="pl-players", on_change=pl_new_players)
    pl_template_card()
    datas, trains, matches = pl_plans(players)
    pl_data_card(players, datas)
    pl_train_card(players, trains)
    pl_match_card(players, matches, trains)
    pl_run_card(players, datas, trains, matches)
    pl_persist()


PAGES = [("data", TAB_DATA, "🎲", lambda: data_tab(), t("section.flow")),
         ("train", TAB_TRAIN, "🧠", lambda: training_tab(), None),
         ("match", TAB_MATCH, "⚔️", lambda: match_tab(), None),
         ("pipeline", t("page.pipeline"), "🔗", lambda: pipeline_page(), None),
         ("modellist", TAB_MODELLIST, "📋", lambda: model_list_page(), t("section.manage")),
         ("models", TAB_MODELS, "📦", lambda: models_tab(), None),
         ("queue", TAB_QUEUE, "🗂️", lambda: queue_page(), None),
         ("hash", t("page.hash"), "🔑", lambda: hash_page(), t("section.help")),
         ("versions", t("page.versions"), "🏷️", lambda: versions_page(), None)]


def current_page():
    ids = [p[0] for p in PAGES]
    page = st.session_state.get("page") or st.query_params.get("page")
    return page if page in ids else ids[0]


def go(page):
    st.session_state["page"] = page
    st.query_params["page"] = page  # a reload stays on the same page


def switch_language():
    other = "zh-TW" if lang() == "en" else "en"
    st.session_state["lang"] = other
    st.query_params["lang"] = other


def sidebar_nav(page):
    st.markdown(f'<div class="nav-brand"><span class="nav-icon">🌱</span><span>Puerto Rico<br>Machine Learning</span></div>',
                unsafe_allow_html=True)
    for pid, title, icon, _, section in PAGES:
        if section:
            st.markdown(f'<div class="navsec">{section}</div>', unsafe_allow_html=True)
        # the active entry gets another key prefix (navon-) so the CSS can highlight it
        st.button(f"{icon} {title}", key=f"{'navon' if pid == page else 'nav'}-{pid}", width="stretch",
                  on_click=go, args=(pid,))
    st.button(t("lang.switch"), key="lang-toggle", on_click=switch_language)


def main():
    st.set_page_config(page_title=TITLE, page_icon="🌱", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    page = current_page()
    with st.sidebar:
        sidebar_nav(page)
        with st.container(key="side-status"):  # pinned to the bottom of the navigation (CSS)
            sidebar_status()
    st.title(t(f"page.{page}"))
    st.caption(t("header.flow", data=TAB_DATA, train=TAB_TRAIN, match=TAB_MATCH, url=DASHBOARD_URL))
    started = st.session_state.pop("job-started", None)
    if started:
        st.toast(started)
    next(p for p in PAGES if p[0] == page)[3]()


main()
