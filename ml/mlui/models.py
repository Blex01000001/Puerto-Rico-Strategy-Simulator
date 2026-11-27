"""Management page 估值模型 (id models): model list, details, comparison and multi-chart views."""

import glob
import hashlib
import json
import os
import re

import streamlit as st
import altair as alt
import pandas as pd

import fingerprint
import jobs
import modelmeta

from mlui.text import (  # noqa: F401
    lang,
    t,
)
from mlui.common import (  # noqa: F401
    match_item,
    open_in_pipeline,
    DASHBOARD_URL,
    LOCAL_CONFIGS,
    LOCAL_MATCHES,
    LOCAL_MODELS,
    MODELS_DIR,
    ROOT,
    best_marker,
    best_vs_default,
    busy_files,
    card,
    delete_button,
    delete_gen,
    describe_match,
    digest_box,
    dump_column_config,
    filter_bar,
    folder_line,
    grid,
    job_reads,
    job_title,
    kind_text,
    list_dumps,
    loss_chart,
    match_columns,
    match_summary_box,
    matches_frame,
    model_files,
    model_meta,
    model_name_taken,
    model_stale,
    pending_readers,
    place_of,
    plain,
    read_config,
    rel,
    tracked_by_git,
    version_table,
    version_tiles,
)


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
            col("model"): name, col("place"): places[place_of(p)], col("kind"): kind_text().get(meta["kind"], meta["kind"]), col("players"): meta["players"],
            col("feature"): meta.get("featureVersion"),
            col("rows"): sum(d["rows"] for d in meta["data"]),
            col("selfplay"): t("common.list").join(sorted({os.path.basename(m) for d in meta["data"] for m in d.get("valueModels", [])})),
            col("r2"): v.get("r2"), col("ce"): v.get("crossEntropy"),
            col("matches"): len(meta.get("matches", [])),
            col("best"): best["winShare"] if best else None,
            col("rules"): fingerprint.rules_name(meta.get("rulesRevision", 1)),
            col("note"): t("mlist.params_backfilled") if "note" in meta.get("params", {}) else (t("mlist.old_record") if not meta.get("fingerprint") else ""),
            col("hash"): fingerprint.short(meta.get("fingerprint")) or "—",
        })
    df = pd.DataFrame(rows)
    # text columns so that missing values read "—" instead of Streamlit's grey "None"
    fmt = {col("r2"): "{:.3f}", col("ce"): "{:.4f}", col("best"): "{:.1%}", col("rows"): "{:,.0f}", col("players"): "{:.0f}", col("matches"): "{:.0f}", col("feature"): "{:.0f}"}
    for name, f in fmt.items():
        if name in df:
            df[name] = [f.format(v) if v is not None and v == v else "—" for v in df[name]]
    return df.fillna("")


def flat_params(meta):
    return {k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in (meta.get("params") or {}).items()}


def move_buttons(path, c_rename, c_move):
    """Rename, and make official (local -> ml/models, then commit it) / move to local (an official-folder model git does not track), in the
    two cells of the action row. path=None (nothing or several ticked): the buttons are off. Returns the note to show under the row."""
    if path is None:
        c_rename.button(t("md.rename"), key="rename-off", disabled=True, width="stretch")
        c_move.button(t("md.promote"), key="move-off", disabled=True, width="stretch")
        return ""
    name = os.path.basename(path)
    if place_of(path) == "local":
        if c_rename.button(t("md.rename"), key=f"rename-{name}", width="stretch"):
            rename_dialog(path)
        with c_move.popover(t("md.promote"), width="stretch"):
            st.markdown(t("md.promote_text", name=name))
            if st.button(t("md.promote_ok"), type="primary", key=f"promote-{name}"):
                try:
                    modelmeta.move_model(path, MODELS_DIR)
                    st.session_state["job-started"] = t("md.promoted", name=name)
                    st.session_state["del-gen"] = delete_gen() + 1
                    st.cache_data.clear()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        return f'<span class="act-note">{t("md.local_note")}</span>'
    c_rename.button(t("md.rename"), key=f"rename-{name}", disabled=True, width="stretch")  # official models are in git
    if not tracked_by_git([path]):
        if c_move.button(t("md.demote"), key=f"demote-{name}", width="stretch"):
            try:
                modelmeta.move_model(path, LOCAL_MODELS)
                st.session_state["job-started"] = t("md.demoted", name=name)
                st.session_state["del-gen"] = delete_gen() + 1
                st.cache_data.clear()
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        return f'<span class="act-note">{t("md.demote_note")}</span>'
    c_move.button(t("md.promote"), key=f"move-off-{name}", disabled=True, width="stretch")
    return ""


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


def rename_dialog(path):
    st.dialog(t("md.rename_title"))(_rename_dialog)(path)


def _rename_dialog(path):
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
            st.session_state["del-gen"] = delete_gen() + 1  # the table rows are renumbered: drop the selection
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
                     col("strategies"): t("common.list").join(dict.fromkeys(strategies)),
                     col("rules"): fingerprint.rules_name(d.get("rulesRevision", 1), d.get("ruleset")),
                     col("commit"): disk["引擎 commit"] if same else "—", "hash": fingerprint.short(d.get("fingerprint")) or "—"})
    return pd.DataFrame(rows)


def model_detail(path):
    meta = model_meta(path)
    name = os.path.basename(path)
    if not meta:
        st.warning(t("md.no_meta", name=name))
        return
    v = meta.get("validation") or {}
    best = best_vs_default(meta)
    st.markdown(version_tiles([(t("mlist.col.kind"), kind_text().get(meta["kind"], meta["kind"])),
                               steps_tile(meta),
                               (t("mlist.col.rows"), f"{sum(d['rows'] for d in meta['data']):,}"),
                               ("R²", f"{v['r2']:.3f}" if v.get("r2") is not None else "—", metric_help("R²")),
                               (t("mlist.col.ce"), f"{v['crossEntropy']:.4f}" if v.get("crossEntropy") is not None else "—", metric_help("交叉熵")),
                               (t("mlist.col.best"), f"{best['winShare']:.1%}" if best else "—")], centre=True), unsafe_allow_html=True)
    st.caption(t("md.best_from", desc=describe_match(best)) if best else t("md.no_best"))

    st.markdown(t("md.matches_title"))
    mf = matches_frame(meta, path)
    if mf.empty:
        st.caption(t("md.no_matches"))
    else:
        grid(mf, full=True, hide_index=True, width="stretch",
                     column_config=match_columns())
        st.caption(t("md.dash_note", url=DASHBOARD_URL))
        match_summary_box(meta, path, f"detail-{name}")

    st.markdown(t("md.data_title"))
    df = model_data_table(meta)
    grid(df, full=True, hide_index=True, width="stretch", column_config=dump_column_config())
    if meta.get("data"):
        folder_line(os.path.dirname(meta["data"][0]["path"].replace("\\", "/")) + "/", f"model-data-{name}")

    left, right = st.columns(2)
    with left:
        st.markdown(t("md.params_title"))
        extra = model_steps_row(meta)
        grid(pd.DataFrame(list(flat_params(meta).items()) + ([extra] if extra else []), columns=[t("md.pcol.param"), t("md.pcol.value")]).astype(str),
             full=True, hide_index=True, width="stretch")
    with right:
        st.markdown(t("md.valid_title"))
        if v.get("byRound"):
            grid(pd.DataFrame(v["byRound"]).rename(columns={"rounds": t("md.vcol.rounds"), "rows": t("md.vcol.rows"), "mse": "MSE"}),
                 full=True, hide_index=True, width="stretch")
        else:
            st.caption(t("md.no_record"))
        st.caption(t("md.valid_note"))

    training = meta.get("training") or {}
    curve = training.get("validLossCurve")
    best_step = (training.get("bestEpoch") if meta.get("kind") == "mlp" else training.get("bestIteration")) or None
    gains = feature_gains(path, meta)
    feats = meta.get("topFeatures") or []
    left, right = st.columns(2)
    with left:
        st.markdown(t("md.curve_title"))
        if curve:
            train_curve = training.get("trainLossCurve")
            st.altair_chart(loss_chart(curve, height=240, best=best_step, train=train_curve), width="stretch")
            gap = gap_text(curve, train_curve)
            tail = tail_gain_text(curve)
            if gap or tail:
                st.caption(" ".join(x for x in (gap, tail) if x))
            if gap:
                st.caption(t("md.gap_note"))
            gchart, window = gain_chart(curve, best=best_step)
            if gchart is not None:
                st.markdown(t("md.gain_title", w=window))
                st.altair_chart(gchart, width="stretch")
                st.caption(t("md.gain_note"))
        else:
            st.caption(t("md.no_curve"))
    with right:
        st.markdown(t("md.feat_title"))
        if gains:
            summary, top_df, fam_df = feature_importance_view(gains)
            st.caption(summary)
            st.altair_chart(share_bars(top_df, 26 * len(top_df) + 50), width="stretch")
            st.markdown(t("md.fam_title"))
            st.altair_chart(share_bars(fam_df, 24 * len(fam_df) + 40), width="stretch")
            st.caption(t("md.fam_note"))
        elif feats:  # the model file is gone: only the top of the metadata
            fd = pd.DataFrame(feats[:10])
            chart = alt.Chart(fd).mark_bar().encode(x=alt.X("gain:Q", title="gain"),
                                                    y=alt.Y("name:N", sort="-x", title=None),
                                                    tooltip=["name", alt.Tooltip("gain:Q", format=",.0f")])
            st.altair_chart(chart.properties(height=300), width="stretch")
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


def loss_win_frame(paths):
    """One row per model that has both a validation cross-entropy and a match result: name, ce, win (best win rate vs the original MCTS),
    players, kind, rows."""
    rows = []
    for p in paths:
        meta = model_meta(p)
        if not meta:
            continue
        ce, best = (meta.get("validation") or {}).get("crossEntropy"), best_vs_default(meta)
        if ce is None or not best:
            continue
        rows.append({"name": os.path.basename(p), "ce": float(ce), "win": float(best["winShare"]), "players": str(meta["players"]),
                     "kind": kind_text().get(meta["kind"], meta["kind"]), "rows": sum(d["rows"] for d in meta["data"])})
    return pd.DataFrame(rows, columns=["name", "ce", "win", "players", "kind", "rows"])


def models_scatter(paths):
    """Validation cross-entropy against the best win rate, one point per model: does a lower loss go with a stronger model? The correlation is
    per player count (needs 3 models; with so few points it is only a hint)."""
    df = loss_win_frame(paths)
    if len(df) < 2:
        st.caption(t("md.sc_none"))
        return
    ce, win, pl, kind = t("mlist.col.ce"), t("mlist.col.best"), t("mlist.col.players"), t("mlist.col.kind")
    shown = df.rename(columns={"ce": ce, "win": win, "players": pl, "kind": kind})
    chart = alt.Chart(shown).mark_point(filled=True, size=90, opacity=.9).encode(
        x=alt.X(f"{ce}:Q", scale=alt.Scale(zero=False), axis=alt.Axis(format=".3f")),
        y=alt.Y(f"{win}:Q", scale=alt.Scale(zero=False), axis=alt.Axis(format=".0%")),
        color=alt.Color(f"{pl}:N", scale=alt.Scale(range=["#4aa8ff", "#e8672f"])), shape=alt.Shape(f"{kind}:N"),
        tooltip=[alt.Tooltip("name:N", title=t("mlist.col.model")), alt.Tooltip(f"{ce}:Q", format=".4f"), alt.Tooltip(f"{win}:Q", format=".1%"),
                 alt.Tooltip("rows:Q", title=t("mlist.col.rows"), format=",")])
    st.altair_chart(chart.properties(height=320), width="stretch")
    notes = []
    for players, g in shown.groupby(pl):
        if len(g) >= 3 and g[ce].nunique() > 1 and g[win].nunique() > 1:
            notes.append(t("md.sc_corr", players=players, n=len(g), r=f"{g[ce].corr(g[win]):+.2f}"))
    st.caption(t("md.sc_note") + (" " + t("common.sep").join(notes) + ("。" if lang() == "zh-TW" else ".") if notes else ""))


def forest_chart(df, fair=None):
    """Win rate of each model with its 95% interval (a dot and a bar), the best on top; `fair` = the even share of a seat (a dashed line).
    Bars that overlap: the difference may be only noise."""
    d = df.sort_values("win", ascending=False).copy()
    d["lo"], d["hi"] = d["win"] - d["ci"], d["win"] + d["ci"]
    order = list(d["name"])
    win = t("mc.win")
    lo = min(float(d["lo"].min()), fair if fair is not None else 1.0) - 0.04
    hi = float(d["hi"].max()) + 0.1
    base = alt.Chart(d).encode(y=alt.Y("name:N", sort=order, title=None, axis=alt.Axis(labelLimit=320, labelOverlap=False)))
    tip = [alt.Tooltip("name:N", title=t("mlist.col.model")), alt.Tooltip("win:Q", title=win, format=".1%"), alt.Tooltip("ci:Q", title="±95%", format=".1%"),
           alt.Tooltip("games:Q", title=t("mt.games"), format=",")]
    bars = base.mark_rule(color="#4aa8ff", strokeWidth=2.5).encode(
        x=alt.X("lo:Q", scale=alt.Scale(domain=[max(lo, 0), min(hi, 1)], nice=False), axis=alt.Axis(format=".0%", title=win)), x2="hi:Q", tooltip=tip)
    dots = base.mark_point(filled=True, size=110, color="#4aa8ff", opacity=1).encode(x="win:Q", tooltip=tip)
    text = base.mark_text(align="left", dx=8, color="#eef1f5", fontSize=11).encode(x="hi:Q", text=alt.Text("win:Q", format=".1%"), tooltip=alt.value(None))
    layers = [bars, dots, text]
    if fair is not None:
        ref = pd.DataFrame({"x": [fair], "tip": [t("mc.fair", p=f"{fair:.0%}")]})
        layers += [alt.Chart(ref).mark_rule(color="#8892a2", strokeDash=[4, 3]).encode(x="x:Q", tooltip=alt.value(None)),
                   alt.Chart(ref).mark_text(align="left", baseline="top", dx=4, dy=2, color="#8892a2", fontSize=10).encode(x="x:Q", y=alt.value(0), text="tip:N",
                                                                                                                     tooltip=alt.value(None))]
    return alt.layer(*layers).properties(height=max(120, 34 * len(d) + 50), padding={"left": 8, "right": 28, "top": 10, "bottom": 6})


def compare_scatter(df, xcol, xtitle, height=340):
    """Win rate (with its 95% interval) against one numeric column of the models, every dot named."""
    d = df.dropna(subset=[xcol]).copy()
    d["lo"], d["hi"] = (d["win"] - d["ci"]).clip(lower=0), (d["win"] + d["ci"]).clip(upper=1)
    win = t("mc.win")
    base = alt.Chart(d)
    tip = [alt.Tooltip("name:N", title=t("mlist.col.model")), alt.Tooltip(f"{xcol}:Q", title=xtitle), alt.Tooltip("win:Q", title=win, format=".1%"),
           alt.Tooltip("ci:Q", title="±95%", format=".1%")]
    x = alt.X(f"{xcol}:Q", scale=alt.Scale(zero=False, nice=True), axis=alt.Axis(title=xtitle))
    y = alt.Y("lo:Q", scale=alt.Scale(zero=False, nice=True), axis=alt.Axis(format=".0%", title=win))
    bars = base.mark_rule(color="#4aa8ff", strokeWidth=2, opacity=.7).encode(x=x, y=y, y2="hi:Q", tooltip=tip)
    dots = base.mark_point(filled=True, size=100, color="#4aa8ff", opacity=1).encode(x=x, y="win:Q", tooltip=tip)
    names = base.mark_text(align="left", dx=8, dy=-8, color="#b4bcc9", fontSize=10).encode(x=x, y="win:Q", text="name:N", tooltip=alt.value(None))
    return alt.layer(bars, dots, names).properties(height=height, padding={"left": 8, "right": 60, "top": 12, "bottom": 6})


MAX_COMPARE = 20   # models the multi-chart view takes (more dots make the names overlap)


def view_switch(key, labels):
    """A row of segmented buttons that works as tabs: only the selected view is drawn, and the choice stays over reruns (labels: {id: text})."""
    ids = list(labels)
    with st.container(key=f"filterbar-{key}"):  # the look of the quick filters (CSS .st-key-filterbar*)
        value = st.segmented_control(key, ids, default=ids[0], selection_mode="single", key=key, format_func=labels.get, label_visibility="collapsed")
    return value or ids[0]


def models_multi(paths):
    """The ticked models side by side in charts: win rates with their intervals under one match condition, win rate against a parameter
    (trees, leaves, learning rate, rows ...) and against what the model costs (time, size), and validation loss against win rate."""
    if len(paths) < 2:
        st.caption(t("mv.pick"))
        return
    if len(paths) > MAX_COMPARE:
        st.caption(t("mv.max", n=len(paths), max=MAX_COMPARE))
        return
    metas = {os.path.basename(p): model_meta(p) for p in paths}
    metas = {n: m for n, m in metas.items() if m}
    if len(metas) < 2:
        st.caption(t("mc.none"))
        return
    view = view_switch("mv-sub", {"forest": t("mc.tab.forest"), "param": t("mc.tab.param"), "cost": t("mc.tab.cost"), "scatter": t("mc.tab.scatter")})
    if view == "scatter":
        models_scatter([p for p in paths if os.path.basename(p) in metas])
        return
    conditions = modelmeta.comparison_conditions(metas)
    if not conditions:
        st.caption(t("mc.no_condition"))
        return
    labels = {c: f"{describe_match(sample)}（{t('mc.n_models', n=n)}）" if lang() == "zh-TW" else f"{describe_match(sample)} ({t('mc.n_models', n=n)})"
              for c, sample, n in conditions}
    sig = hashlib.md5(".".join(sorted(metas)).encode()).hexdigest()[:8]   # another set of ticked models: the condition list starts again
    condition = st.selectbox(t("mc.condition"), list(labels), format_func=labels.get, key=f"mc-cond-{sig}")
    rows = pd.DataFrame(modelmeta.comparison_rows(metas, condition))
    sides = {int(x) for x in rows["players"]}
    fair = 1 / sides.pop() if len(sides) == 1 else None

    def scatter_view(options, key, note):
        usable = {label: col for label, col in options.items() if rows[col].dropna().nunique() >= 2}
        if not usable:
            st.caption(t("mc.no_x"))
            return
        label = st.selectbox(t("mc.pick_x"), list(usable), key=key)
        st.altair_chart(compare_scatter(rows, usable[label], label), width="stretch")
        missing = [n for n, v in zip(rows["name"], rows[usable[label]]) if v != v or v is None]  # no value recorded: not drawn
        st.caption(note + (" " + t("mc.missing", names=t("common.list").join(missing)) if missing else ""))

    if view == "forest":
        st.altair_chart(forest_chart(rows, fair), width="stretch")
        st.caption(t("mc.forest_note"))
    elif view == "param":
        scatter_view({t("mc.x.trees"): "trees", t("mc.x.grown"): "grown", t("mc.x.leaves"): "leaves", t("mc.x.lr"): "learningRate",
                      t("mc.x.minleaf"): "minLeaf", t("mc.x.rounds"): "rounds", t("mc.x.rows"): "rows"}, f"mc-x-param-{sig}", t("mc.param_note"))
    else:
        scatter_view({t("mc.x.match_sec"): "matchSecPerGame", t("mc.x.train_sec"): "trainSeconds", t("mc.x.size"): "size"}, f"mc-x-cost-{sig}", t("mc.cost_note"))


def models_page():
    """The list (quick filters, tick rows) with the actions on the ticked rows, then the details of the ticked model (one: its
    details, two to four: side by side). Rename, make official / move to local, delete and copy-for-AI live here only."""
    paths = model_files()
    if not paths:
        st.info(t("md.none"))
        return
    with card("models-list", t("mlist.card"), t("mlist.card_sub")):
        chosen = models_list()
    with card("models"):
        view = view_switch("mv-view", {"detail": t("mv.detail"), "multi": t("mv.multi")})
        if view == "multi":
            models_multi(chosen)
        elif not chosen:
            st.caption(t("md.select_hint"))
        elif len(chosen) == 1:
            model_detail(chosen[0])
        elif len(chosen) <= 4:
            compare(chosen)
        else:
            st.caption(t("md.pick_max"))
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
        return []
    table = models_table(paths)
    col = lambda key: t(f"mlist.col.{key}")  # noqa: E731
    rules_opts = sorted({r for r in table[col("rules")] if r}) if col("rules") in table else []
    places, kinds, players, rules = filter_bar("mf", [(t("mlist.place"), ["git", "local"], "mf-place", None), (t("mlist.kind"), ["LightGBM", "MLP"], "mf-kind", None),
                                                      (t("mlist.players"), ["3", "4"], "mf-players", lambda n: t("match.players_n", n=n)),
                                                      (t("mlist.rules"), rules_opts, "mf-rules", None)])
    keep = (table[col("place")].isin(places or ["git", "local"]) & table[col("kind")].isin(kinds or ["LightGBM", "MLP"])
            & table[col("players")].isin(players or ["3", "4"]))
    if rules:  # models without metadata have no rules version: they only show while no rules filter is selected
        keep &= table[col("rules")].isin(rules)
    shown = table[keep]
    shown_paths = [p for p, k in zip(paths, keep) if k]
    if shown.empty:
        st.caption(t("mlist.none"))
        return []
    centred = {c: st.column_config.TextColumn(c, alignment="center") for c in (col("players"), col("feature"), col("rules"), col("r2"), col("ce"), col("matches"), col("best"))
               if c in shown}
    # a selection is by row number: the filters and the deletion counter are part of the key
    picked = grid(shown, hide_index=True, width="stretch", column_config=centred, on_select="rerun", selection_mode="multi-row",
                  key=f"models-list-{delete_gen()}-{'.'.join(places or [])}-{'.'.join(kinds or [])}-{'.'.join(players or [])}-{'.'.join(rules or [])}")
    chosen = [shown_paths[i] for i in picked.selection.rows]
    st.caption(t("mlist.footer", shown=len(shown), total=len(table)))
    items = []
    for m in chosen:
        meta = model_meta(m)
        items.append(modelmeta.model_digest(os.path.basename(m), meta, model_stale(meta)) if meta else f"M {os.path.basename(m)} (no metadata)")
    busy = {f for j in jobs.list_jobs() if j["state"] in ("waiting",) + jobs.BUSY for f in job_reads(j)}
    busy |= busy_files("out")  # a training job that is writing it
    files = [p for m in chosen for p in [m, os.path.join(modelmeta.local_records_dir(), os.path.basename(m) + ".matches.json")]
             if os.path.exists(p)]  # the model and the match records kept beside it (official models' records are local)
    # the action bar: rename | make official / move to local | copy details | hint ........ delete (rename and move: exactly one ticked model)
    with st.container(key="actionbar-models"):
        c_rename, c_move, c_match, c_copy, c_hint, c_delete = st.columns([1.2, 1.7, 1.7, 1.9, 2.3, 1.7], vertical_alignment="center")
        note = move_buttons(chosen[0] if len(chosen) == 1 else None, c_rename, c_move)
        # 對戰這個模型: one match item (this model against plain MCTS) in 建立排程
        one = model_meta(chosen[0]) if len(chosen) == 1 else None
        if one and one.get("players") in (3, 4):
            name = os.path.basename(chosen[0])
            c_match.button(t("md.to_match"), key="md-to-match", width="stretch", help=t("md.to_match_help", page=t("page.pipeline")),
                           on_click=open_in_pipeline, args=("m", match_item(name, one["players"]), one["players"], t("pl.prefill.match", name=name)))
        else:
            c_match.button(t("md.to_match"), key="md-to-match", width="stretch", disabled=True, help=t("md.to_match_help", page=t("page.pipeline")))
        hint = digest_box(modelmeta.digest(items) if chosen else "", "models", len(chosen), c_copy)
        if hint:
            c_hint.markdown(hint, unsafe_allow_html=True)
        with c_delete:
            delete_button("del-models", t("del.button", n=len(chosen)), files, extra_suffixes=(".meta.json", ".check.txt"), busy=busy)
    if note:
        st.markdown(note, unsafe_allow_html=True)
    st.caption(t("mlist.delete_hint") + (" " + t("mlist.delete_official") if any(place_of(m) == "official" for m in chosen) else ""))
    return chosen


def gap_text(values, train):
    """'Final loss: training X, validation Y, gap Z (p%)' under the curve; None without a training curve."""
    if not train or len(train) != len(values):
        return None
    gap = values[-1] - train[-1]
    return t("md.gap_text", train=f"{train[-1]:.4f}", valid=f"{values[-1]:.4f}", gap=f"{gap:+.4f}", pct=f"{gap / values[-1]:+.2%}" if values[-1] else "—")


def gain_series(values, steps=None, window=20):
    """Loss improvement per step, averaged over the last `window` steps: [(step, improvement)] (positive = the loss went down)."""
    steps = list(steps) if steps is not None else list(range(1, len(values) + 1))
    w = max(1, min(window, len(values) // 5 or 1))
    return w, [(steps[i], (values[i - w] - values[i]) / w) for i in range(w, len(values))]


def gain_chart(values, best=None, height=190):
    """How much each further round still improves the validation loss (the answer to 'would more trees help?'): a symlog axis shows the
    early big steps and the late tiny ones in one picture; zero and below = no gain."""
    w, rows = gain_series(values)
    if len(rows) < 2:
        return None, w
    step, ylab = t("md.step"), t("md.gain_y")
    df = pd.DataFrame(rows, columns=["s", "g"])
    first, last = float(df["s"].min()), float(df["s"].max())
    yscale = alt.Scale(type="symlog", constant=1e-6)
    x = alt.X("s:Q", axis=alt.Axis(tickMinStep=1, format="d", title=step), scale=alt.Scale(domain=[first, last], nice=False))
    y = alt.Y("g:Q", scale=yscale, axis=alt.Axis(title=ylab, format=".5~f", values=[0, 1e-5, 1e-4, 1e-3, 1e-2], labelOverlap=False))
    no_tip, grey = alt.value(None), "#8892a2"
    nearest = alt.selection_point(nearest=True, on="mouseover", clear="mouseout", encodings=["x"], empty=False)   # the crosshair, as in the loss chart
    base = alt.Chart(df).encode(x=x, y=y)
    line = base.mark_line(color="#3fa83f", strokeWidth=2).encode(tooltip=no_tip)
    zero = alt.Chart(pd.DataFrame({"g": [0.0]})).mark_rule(color=grey, strokeDash=[4, 3]).encode(y=alt.Y("g:Q", scale=yscale), tooltip=no_tip)
    hit = alt.Chart(df).mark_point(opacity=0).encode(x=x, tooltip=no_tip).add_params(nearest)
    vrule = alt.Chart(df).mark_rule(color=grey, strokeDash=[4, 3]).encode(x=x, tooltip=no_tip).transform_filter(nearest)
    hrule = alt.Chart(df).mark_rule(color=grey, strokeDash=[4, 3]).encode(y=alt.Y("g:Q", scale=yscale), tooltip=no_tip).transform_filter(nearest)
    dot = base.mark_point(color="#fff", fill="#fff", filled=True, size=60).encode(tooltip=no_tip).transform_filter(nearest)
    text = f"{json.dumps(step, ensure_ascii=False)} + ' ' + datum.s + ' ・ ' + format(datum.g, '.6f')"
    mid = (first + last) / 2
    labels = [base.mark_text(align=align, dx=dx, dy=-12, color="#eef1f5", fontSize=12, fontWeight="bold").encode(text="tip:N", tooltip=no_tip)
              .transform_calculate(tip=text).transform_filter(nearest).transform_filter(cond)
              for align, dx, cond in (("left", 8, f"datum.s <= {mid}"), ("right", -8, f"datum.s > {mid}"))]
    layers = [line, zero, hit, vrule, hrule, dot, *labels]
    if best is not None and best >= first:
        layers += best_marker(best, x, no_tip)
    return alt.layer(*layers).properties(height=height, padding={"left": 12, "right": 18, "top": 14, "bottom": 10}), w


def tail_gain_text(values, k=100):
    """'The last k steps improved the validation loss by d (p%)' for the caption under the curve; None for a very short curve."""
    if len(values) < 3:
        return None
    k = min(k, len(values) - 1)
    d = values[-1 - k] - values[-1]
    return t("md.tail_gain", k=k, d=f"{d:.5f}", pct=f"{d / values[-1 - k]:.2%}" if values[-1 - k] else "—")


FEATURE_PREFIX = re.compile(r"^p\d_")


def feature_family(name):
    """The family of a feature: its name without the seat prefix (p0_) and the item suffix and digits: p0_tiles_Corn, p2_tiles_Sugar -> tiles,
    ship1_load -> ship, governorRel2 -> governorRel."""
    return re.sub(r"\d+$", "", FEATURE_PREFIX.sub("", name).split("_")[0])


@st.cache_data(show_spinner=False)
def _model_gains(path, stamp):
    """(feature names, gains) of a LightGBM model file, read from the file (the metadata keeps only the top 30). `stamp` makes a new file miss the cache."""
    import lightgbm as lgb
    booster = lgb.Booster(model_file=path)
    return booster.feature_name(), [float(g) for g in booster.feature_importance("gain")]


def feature_gains(path, meta):
    """[(feature, gain)] of every feature of a LightGBM model (from the model file), or None (MLP, or the file is gone)."""
    if meta.get("kind") == "mlp" or not os.path.exists(path):
        return None
    try:
        names, gains = _model_gains(path, os.path.getmtime(path))
    except Exception:  # an unreadable file is the same as none
        return None
    return list(zip(names, gains))


def feature_importance_view(gains, top=10, families=15):
    """(summary text, top-features frame, family frame) of [(feature, gain)]: shares of the total gain, the count of unused (gain 0) features, the
    top `top` features and the `families` biggest families (the rest as one 'other' row)."""
    total = sum(g for _, g in gains) or 1.0
    unused = sum(1 for _, g in gains if g <= 0)
    summary = t("md.feat_summary", n=len(gains), used=len(gains) - unused, unused=unused)
    best = sorted(gains, key=lambda x: -x[1])[:top]
    top_df = pd.DataFrame({"name": [n for n, _ in best], "gain": [g for _, g in best], "share": [g / total for _, g in best]})
    fam = {}
    for n, g in gains:
        f = feature_family(n)
        fam[f] = fam.get(f, 0.0) + g
    rows = sorted(fam.items(), key=lambda x: -x[1])
    keep, rest = rows[:families], rows[families:]
    if rest:
        keep.append((t("md.fam_other"), sum(g for _, g in rest)))
    fam_df = pd.DataFrame({"name": [n for n, _ in keep], "share": [g / total for _, g in keep]})
    return summary, top_df, fam_df


def share_bars(df, height, title=None):
    """Horizontal bars of `share` (percent of the total gain) with the percentage written at the end of each bar; the order is the frame's."""
    order = list(df["name"])
    base = alt.Chart(df).encode(y=alt.Y("name:N", sort=order, title=None, axis=alt.Axis(labelLimit=260, labelOverlap=False, labelFontSize=11)))
    bars = base.mark_bar(color="#4aa8ff").encode(
        x=alt.X("share:Q", title=title or t("md.feat_share"), axis=alt.Axis(format=".0%")),
        tooltip=[alt.Tooltip("name:N", title=t("md.pcol.param")), alt.Tooltip("share:Q", title=t("md.feat_share"), format=".2%")]
        + ([alt.Tooltip("gain:Q", title="gain", format=",.0f")] if "gain" in df else []))
    text = base.mark_text(align="left", dx=4, color="#eef1f5", fontSize=11).encode(x="share:Q", text=alt.Text("share:Q", format=".1%"), tooltip=alt.value(None))
    return (bars + text).properties(height=height)


def steps_tile(meta):
    """Tile with the trees (LightGBM) or epochs (MLP) of a model as actual/trained: how many the training really grew or ran / how many it was
    told to (early stopping ends it sooner). What the saved model keeps (up to the best round) is a row of the parameter table (`model_steps_row`)."""
    tr, params = meta.get("training") or {}, meta.get("params") or {}
    if meta.get("kind") == "mlp":
        actual, planned = tr.get("epochsRun"), params.get("epochs")
        label, tip = t("md.epochs"), t("md.help.epochs")
    else:
        actual = len(tr.get("validLossCurve") or []) or tr.get("iterations")
        planned = params.get("num_boost_round")
        label, tip = t("md.trees"), t("md.help.trees", stop=params.get("early_stopping_rounds", "—"))
    return (label, f"{actual}/{planned if planned is not None else '—'}" if actual is not None else "—", tip)


def model_steps_row(meta):
    """The trees the saved model keeps (LightGBM: the best round, the rest of an early-stopped run is dropped) or its best epoch (MLP), as a
    (name, value) row for the parameter table; None when the metadata has no record."""
    tr = meta.get("training") or {}
    if meta.get("kind") == "mlp":
        return (t("md.row.best_epoch"), tr["bestEpoch"]) if tr.get("bestEpoch") is not None else None
    return (t("md.row.model_trees"), tr["iterations"]) if tr.get("iterations") is not None else None


def metric_help(name):
    return {"R²": t("md.help.r2"), "交叉熵": t("md.help.ce")}[name]
