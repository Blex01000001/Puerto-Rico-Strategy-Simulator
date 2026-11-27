"""Shared by the ML UI pages: paths, files on disk, jobs, widgets (cards, tables, buttons, filters), charts and helpers.
A name lives here when two or more pages (or the navigation) use it; a page's own helpers are in its module."""

import datetime
import html
import glob
import json
import os
import time

import streamlit as st
import altair as alt
import pandas as pd

import fingerprint
import folders
import jobs
import modelmeta
import positions

from mlui.text import (  # noqa: F401
    lang,
    t,
)


ROOT = jobs.ROOT
MODELS_DIR = os.path.join(ROOT, "ml", "models")                    # official models (tracked by git)
LOCAL_DIR = os.path.join(ROOT, "ml", "local")                      # this machine's workspace (ignored by git)
LOCAL_MODELS = os.path.join(LOCAL_DIR, "models")
LOCAL_CONFIGS = os.path.join(LOCAL_DIR, "data-configs")
LOCAL_MATCHES = os.path.join(LOCAL_DIR, "matches")
DASHBOARD_URL = "http://localhost:5080"


def kind_text():
    return {"train_lgbm": "LightGBM", "train_mlp": "MLP", "lightgbm": "LightGBM", "mlp": "MLP", "dump": t("job.kind.dump"), "match": t("job.kind.match")}


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
            ok, why = folders.open_folder(absolute(path), ROOT, lang())
            if ok:
                st.toast(t("common.folder_opened"))
            else:
                st.toast(why, icon="⚠️")


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
    if "hash" in df:  # the hash is the last column of every data table
        df = df[[c for c in df.columns if c != "hash"] + ["hash"]]
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


PARAM_DEFAULTS = {"rounds": "400", "leaves": "63", "lr": "0.05", "min_leaf": "200", "feature_fraction": "0.8", "bagging_fraction": "0.8", "early_stopping": "30", "threads": "0", "hidden": "256,128", "epochs": "12", "batch": "1024", "l2": "1e-5", "patience": "3", "backend": "auto", "device": "auto", "valid": "0.1", "seed": "1"}  # the default shown in the help text (labels: param.<name>)


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


def grid(data, full=False, **kwargs):
    """st.dataframe with room for a horizontal scrollbar: Streamlit sizes a table to its rows exactly, so on Windows (a
    17 px scrollbar that takes space) the scrollbar of a wide table covered the last row. At most 10 rows are shown
    before the table scrolls vertically; full=True shows every row (no vertical scrolling)."""
    rows = len(getattr(data, "data", data))  # a pandas Styler keeps the frame in .data
    kwargs.setdefault("height", 35 * ((rows if full else min(rows, 10)) + 1) + 2 + 18)
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


FILTER_ALL = "*"


def filter_bar(key, dims):
    """One flat bar of quick filters. dims = [(label, options, widget key, format_func or None)]: each is a label and a segmented control
    (All | option | option ...). Returns one list per dimension: [] for "All" (or nothing selected), [value] otherwise."""
    out = []
    with st.container(key=f"filterbar-{key}"):  # CSS .st-key-filterbar*
        for c, (label, options, wkey, fmt) in zip(st.columns(len(dims), vertical_alignment="center"), dims):
            value = c.segmented_control(label, [FILTER_ALL] + list(options), default=FILTER_ALL, selection_mode="single", key=wkey,
                                        format_func=lambda o, fmt=fmt: t("filter.all") if o == FILTER_ALL else (fmt(o) if fmt else str(o)))
            out.append([] if value in (None, FILTER_ALL) else [value])
    return out


def delete_button(key, label, paths, extra_suffixes=(), busy=()):
    """A red delete button (right-aligned via the 'del-' key prefix) that asks for confirmation in a dialog; files a
    queued or running job needs are refused. A dialog closes with the rerun after deleting (a popover stayed open)."""
    with st.container(key=key):
        if st.button(label, key=f"{key}-open", disabled=not paths):
            confirm_delete(key, list(paths), tuple(extra_suffixes), tuple(busy))


def confirm_delete(key, paths, extra_suffixes, busy):
    st.dialog(t("del.dlg"))(_confirm_delete)(key, paths, extra_suffixes, busy)


def _confirm_delete(key, paths, extra_suffixes, busy):
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


TITLE = "Puerto Rico Machine Learning"


def plain(text):
    """Problem texts may contain `code` marks; the inline hints are plain HTML."""
    import html
    return html.escape(str(text).replace("`", ""))


def action_row(label, key, problems, extra=None):
    """A start button with its hint on the same line, to its right: blue when it can start, locked with the reasons in
    red otherwise; while jobs run, the hint says where the new one will queue. Returns True when clicked."""
    with st.container(key=f"actionbar-{key}"):  # CSS: a line above, like the management pages' action bar
        c1, c2 = st.columns([2.2, 5], vertical_alignment="center")
        clicked = c1.button(start_label(label), type="primary", disabled=bool(problems), key=key, width="stretch")
        _action_hint(c2, problems, extra)
    return clicked


def _action_hint(c2, problems, extra):
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
        st.session_state["job-started"] = t("job.started_queued", pos=pos) if pos else t("job.started_now", page=t("page.queue"))
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
        c1, c2 = st.columns([2.6, 1.4], vertical_alignment="bottom")
        if lost:
            c1.markdown(f'<div class="side-state lost">{t("side.lost")}</div>', unsafe_allow_html=True)
        else:
            c1.progress(frac or 0.0, text=text)
        if c2.button(t("side.end") if lost else t("side.cancel"), key=f"stop-side-{active['id']}", width="stretch",  # stop-: red (CSS)
                     help=t("job.lost_help") if lost else None):
            jobs.cancel(active["id"])
    else:
        st.markdown(f'<div class="side-note">{t("side.idle")}</div>', unsafe_allow_html=True)
    if waiting:
        st.markdown(f'<div class="side-note">{t("side.queued", n=len(waiting))}</div>', unsafe_allow_html=True)


def copy_button(text, label=None):
    """A button that puts `text` on the clipboard without showing it (runs in a small iframe via st.iframe, or components.html on an
    older Streamlit; falls back to execCommand when the browser blocks navigator.clipboard there)."""
    label = label or t("copy.label")
    payload = json.dumps(text, ensure_ascii=False).replace("</", "<\\/")
    page = f"""<!doctype html>
<style>html, body {{ margin: 0; padding: 0; overflow: hidden; background: transparent; }} body {{ padding-top: 5px; }}</style>
<button id="b" style="width:100%;height:34px;border-radius:6px;border:1px solid rgba(240,246,252,.1);background:#1f6feb;color:#fff;
  font:500 13px system-ui,'Microsoft JhengHei',sans-serif;cursor:pointer;white-space:nowrap">{label}</button>
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
def all_strategies():
    """Registered strategies (ml/engine-info.json, written from the engine's registry, so the list never drifts from what
    the Runner accepts), without rule-based: it needs params.profile and is the same as the named hand-written strategies."""
    return [n for n in fingerprint.engine_info().get("strategies", []) if n != "rule-based"]


DEFAULT_CUSTOM = {4: ["cheap-engine", "build-first", "harbor-rush", "corn-to-premium"], 3: ["cheap-engine", "build-first", "harbor-rush"]}


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


def selfplay_config(name, players, games, seed, sims, leaf, model_rel):
    """MCTS + value model at every seat (the data of an iteration)."""
    return {"schemaVersion": 1, "name": name, "players": players, "games": int(games), "seed": int(seed), "seatOrder": "random",
            "seats": [{"id": f"m{i}", "strategy": "mcts", "params": {"simulations": int(sims), "valueModel": model_rel, "leafRollout": int(leaf)}}
                      for i in range(players)],
            "output": {"perGameRecords": False}}


def match_tables():
    return {key: t(f"match.table.{key}") for key in ("default", "hand", "model")}


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
def match_columns():
    return {
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


def digest_box(text, key, n_chosen, container):
    """The copy-details button (label with the number of ticked rows) in `container`, a cell of the action bar. Nothing ticked, or the text
    over modelmeta.DIGEST_LIMIT characters: the button is off. Returns the hint for the bar (how long the text is), '' when nothing is ticked."""
    n, limit = len(text), modelmeta.DIGEST_LIMIT
    over = n > limit
    label = t("digest.copy", n=n_chosen)
    with container:
        if not n_chosen or over:
            with st.container(key=f"digest-off-{key}"):  # CSS: the same blue, dimmed
                st.button(label, key=f"digest-off-{key}-btn", disabled=True, width="stretch")
        else:
            copy_button(text, label)
    if not n_chosen:
        return ""
    return (f'<span class="act-err">{t("digest.over", n=f"{n:,}", limit=f"{limit:,}")}</span>' if over
            else f'<span class="act-note">{t("digest.count", n=f"{n:,}", limit=f"{limit:,}")}</span>')


def _esc(text):
    import html
    return html.escape(str(text))


def loss_chart(values, steps=None, height=240, best=None, train=None):
    """The validation-loss curve as a fixed chart: no zoom or pan, both axes fixed to the data plus a margin on every side (so the line
    never touches the frame), whole steps on the x axis. `train` (same length) adds the training loss as a second line with a legend.
    A crosshair follows the mouse: lines through the nearest point, its step and its loss(es)."""
    steps = list(steps) if steps is not None else list(range(1, len(values) + 1))
    train = list(train) if train is not None and len(train) == len(values) else None
    step, loss = t("md.step"), (t("md.loss") if train else t("md.valid_loss"))
    valid_name, train_name = t("md.series.valid"), t("md.series.train")
    df = pd.DataFrame({"s": steps, "l": list(values)})
    if train:
        df["tr"] = train
    allv = list(values) + (train or [])
    lo, hi = float(min(allv)), float(max(allv))
    ypad = (hi - lo) * 0.12 or max(abs(hi) * 0.02, 0.001)
    first, last = float(min(steps)), float(max(steps))
    xpad = max(0.5, (last - first) * 0.04)
    blue, green, grey = "#4aa8ff", "#3fa83f", "#8892a2"
    x = alt.X("s:Q", scale=alt.Scale(domain=[first - xpad, last + xpad], nice=False), axis=alt.Axis(tickMinStep=1, format="d", title=step))
    yscale = alt.Scale(domain=[lo - ypad, hi + ypad], nice=False, zero=False)
    y = alt.Y("l:Q", scale=yscale, axis=alt.Axis(title=loss, format=".3f"))
    nearest = alt.selection_point(nearest=True, on="mouseover", clear="mouseout", encodings=["x"], empty=False)
    base = alt.Chart(df).encode(x=x, y=y)
    no_tip = alt.value(None)   # Streamlit adds a tooltip with the raw field names to every mark: the labels below say it already
    if train:  # long form for the lines: the colour field makes the legend
        long = pd.concat([pd.DataFrame({"s": steps, "v": list(values), "series": valid_name}), pd.DataFrame({"s": steps, "v": train, "series": train_name})])
        lines = alt.Chart(long).mark_line(strokeWidth=2).encode(
            x=x, y=alt.Y("v:Q", scale=yscale, axis=None),
            color=alt.Color("series:N", scale=alt.Scale(domain=[valid_name, train_name], range=[blue, green]), legend=alt.Legend(title=None, orient="bottom-left", fillColor="#111418", padding=4)),
            tooltip=no_tip)
        line = [lines]
    else:
        line = [base.mark_line(color=blue, strokeWidth=2, point=alt.OverlayMarkDef(color=blue, size=18)).encode(tooltip=no_tip)]
    hit = alt.Chart(df).mark_point(opacity=0).encode(x=x, tooltip=no_tip).add_params(nearest)   # invisible: picks the point nearest to the mouse
    vrule = alt.Chart(df).mark_rule(color=grey, strokeDash=[4, 3]).encode(x=x, tooltip=no_tip).transform_filter(nearest)
    hrule = alt.Chart(df).mark_rule(color=grey, strokeDash=[4, 3]).encode(y=y, tooltip=no_tip).transform_filter(nearest)
    dots = [base.mark_point(color="#fff", fill="#fff", filled=True, size=60).encode(tooltip=no_tip).transform_filter(nearest)]
    text = f"{json.dumps(step, ensure_ascii=False)} + ' ' + datum.s + ' ・ ' + format(datum.l, '.4f')"
    if train:
        text = (f"{json.dumps(step, ensure_ascii=False)} + ' ' + datum.s + ' ・ ' + {json.dumps(valid_name, ensure_ascii=False)} + ' ' + format(datum.l, '.4f')"
                f" + ' / ' + {json.dumps(train_name, ensure_ascii=False)} + ' ' + format(datum.tr, '.4f')")
        dots.append(alt.Chart(df).mark_point(color="#fff", fill="#fff", filled=True, size=60).encode(x=x, y=alt.Y("tr:Q", scale=yscale), tooltip=no_tip)
                    .transform_filter(nearest))
    mid = (first + last) / 2
    labels = [base.mark_text(align=align, dx=dx, dy=-12, color="#eef1f5", fontSize=12, fontWeight="bold").encode(text="tip:N", tooltip=no_tip)
              .transform_calculate(tip=text).transform_filter(nearest).transform_filter(cond)
              for align, dx, cond in (("left", 8, f"datum.s <= {mid}"), ("right", -8, f"datum.s > {mid}"))]
    layers = [*line, hit, vrule, hrule, *dots, *labels]
    if best is not None:
        layers += best_marker(best, x, no_tip)
    chart = alt.layer(*layers)
    return chart.properties(height=height, padding={"left": 12, "right": 18, "top": 14, "bottom": 10})


def best_marker(best, x, no_tip):
    """A dashed orange vertical line at the best step (LightGBM: the best round, MLP: the best epoch) with its label at the top."""
    orange = "#e0a410"
    frame = pd.DataFrame({"s": [best], "tip": [t("md.best_round", n=best)]})
    rule = alt.Chart(frame).mark_rule(color=orange, strokeDash=[6, 3], strokeWidth=1.5).encode(x=x, tooltip=no_tip)
    text = alt.Chart(frame).mark_text(align="right", baseline="top", dx=-5, dy=3, color=orange, fontSize=11).encode(x=x, y=alt.value(0), text="tip:N", tooltip=no_tip)
    return [rule, text]


def version_tiles(items, centre=False):
    """Tiles like the Dashboard's (label small and muted at the top left, value centred): [(label, value)] or
    [(label, value, help)]; a help text puts a "?" at the top right that shows it on hover.
    centre=True: the value is centred in the whole tile (vertically too), not just in the space under the label."""
    def tile(item):
        label, value, tip = (tuple(item) + (None,))[:3]
        q = f'<span class="q" title="{_esc(tip)}">?</span>' if tip else ""
        return f'<div class="vtile"><div class="l">{_esc(label)}</div>{q}<div class="v">{_esc(value)}</div></div>'
    return f'<div class="vtiles{" mid" if centre else ""}">' + "".join(tile(i) for i in items) + "</div>"


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


def go(page):
    """Opens another page of the navigation (on the next run)."""
    if page != st.session_state.get("page"):
        st.session_state["scroll-top"] = True  # the next run draws the new page: start it at the top
    st.session_state["page"] = page
    st.query_params["page"] = page  # a reload stays on the same page


def open_in_pipeline(kind, item, players, note):
    """A shortcut of another page (對戰這個模型, 用這些資料訓練): hands one ready item to the 建立排程 page and opens it.
    The page takes it at its next run (pipeline.pl_take_prefill): another player count starts a new form, otherwise the item is added."""
    st.session_state["pl-prefill"] = {"kind": kind, "item": item, "players": players, "note": note}
    go("pipeline")


def train_item(paths, players, kind="train_lgbm"):
    """A pipeline training item on existing data files (relative paths), with the default options and a time-stamped name."""
    import train_options
    stamp = datetime.datetime.now().strftime("%m%d-%H%M")
    return {"data": list(paths), "kind": kind, "name": f"{players}p-{'lgbm' if kind == 'train_lgbm' else 'mlp'}-{stamp}",
            "options": train_options.defaults(kind)}


def match_item(model_name, players):
    """A pipeline match item: the model against plain MCTS (the 對戰驗證 defaults: 300 simulations, 240 games, seed 9191)."""
    return {"model": model_name, "table": "default", "rival": None, "sims": 300, "leaf": 40 if players == 4 else 0, "bsims": 300,
            "games": 240, "seed": 9191, "threads": 0}
