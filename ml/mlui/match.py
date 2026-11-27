"""Page 對戰驗證 (id match): matches of a value model against plain MCTS, hand-written strategies or another model."""

import json
import os

import streamlit as st

import fingerprint
import jobs

from mlui.text import (  # noqa: F401
    t,
)
from mlui.common import (  # noqa: F401
    LOCAL_MATCHES,
    absolute,
    action_row,
    best_vs_default,
    card,
    grid,
    match_columns,
    match_default_name,
    match_seats,
    match_summary_box,
    match_tables,
    matches_frame,
    model_meta,
    model_path,
    models_for,
    pending_output,
    rel,
    safe_name,
    same_name_notice,
    start_job,
    write_config,
)


def _match_body():
    st.caption(t("match.intro"))
    players = st.radio(t("match.players"), [4, 3], horizontal=True, format_func=lambda n: t("match.players_n", n=n), key="m-players")
    cands = models_for(players)
    if not cands:
        st.info(t("match.no_model", n=players))
        return
    names = [os.path.basename(p) for p in cands]
    model = st.selectbox(t("match.model"), names, index=len(names) - 1, key="m-model")
    table = st.radio(t("match.opponent"), list(match_tables()), format_func=match_tables().get, horizontal=True, key="m-table")
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
                     column_config=match_columns())
        match_summary_box(meta, model_path(model), f"match-{model}")


def match_tab():
    with card("match", t("match.card")):
        _match_body()
