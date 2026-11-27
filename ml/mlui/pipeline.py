"""Page 流程排定 (id pipeline): the widgets of the pipeline (data -> train -> match, queued together).
The checks of an item (no widgets) are in mlui/plan.py; widget-free helpers in ml/pipeline_form.py."""

import datetime
import html
import glob
import json
import os
import re

import streamlit as st
import pandas as pd

import pipeline_form
import fingerprint
import jobs

from mlui.text import (  # noqa: F401
    t,
)
from mlui.common import (  # noqa: F401
    DEFAULT_CUSTOM,
    LOCAL_CONFIGS,
    LOCAL_DIR,
    LOCAL_MATCHES,
    ROOT,
    absolute,
    action_row,
    all_strategies,
    best_vs_default,
    card,
    config_rows,
    delete_button,
    dump_column_config,
    filter_bar,
    grid,
    job_title,
    kind_text,
    match_tables,
    model_meta,
    model_path,
    models_for,
    param_inputs,
    plain,
    read_config,
    rel,
    safe_name,
    write_config,
)
from mlui.plan import (  # noqa: F401
    seat_orders,
    pl_data_plan,
    pl_items,
    pl_known_dumps,
    pl_match_plan,
    pl_plans,
    pl_train_defaults,
    pl_train_plan,
)


# left navigation like the Dashboard: (id, title, icon, page function, section heading shown above it)
# Data sets, models to train and matches are items (dicts in the session state: "pl-data", "pl-train", "pl-match"). An item is set up in a
# dialog; the page shows it read-only, like the summary of an order. To change one, remove it and add it again.

PIPELINES_DIR = os.path.join(LOCAL_DIR, "pipelines")
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


def pl_take_prefill():
    """An item handed over by another page (common.open_in_pipeline): another player count starts a new form, then the item is added.
    Runs before the player radio is drawn, so it may set the player count."""
    pre = st.session_state.pop("pl-prefill", None)
    if not pre:
        return
    if st.session_state.get("pl-players") != pre["players"]:
        st.session_state["pl-players"] = pre["players"]
        _pl_set_lists([], [], [])
    pl_item_add(pre["kind"], pre["item"])
    st.toast(pre["note"])


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




def mcts_first():
    """MCTS parameters shown first, in this order (Engine SeatParams.MctsFirst, via ml/engine-info.json: the Dashboard's order)."""
    return fingerprint.engine_info().get("mctsParamOrder", [])


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
                first = mcts_first()
                keys = [k for k in first if k in keys] + [k for k in keys if k not in first]
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
            item["seat_order"] = pl_select(t("pl.data.seat_order"), list(seat_orders()), "pld-seatorder", default="random", format_func=lambda o: t(f"pl.data.so.{o}"))
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
        kind_opts = [t("pl.train.kind_new_short"), t("pl.train.kind_existing")]
        feature_opts = sorted({r["feature"] for r in all_rows.values()})
        rules_opts = sorted({r["rules"] for r in all_rows.values() if r["rules"]})
        fk, fv, rv = filter_bar("pl-train", [(t("pl.train.col.kind"), kind_opts, "pld-tf-kind", None),
                                              (t("dump.col.feature"), feature_opts, "pld-tf-feature", lambda n: f"v{n}"),
                                              (t("dump.col.rules"), rules_opts, "pld-tf-rules", None)])  # same look as the training page's

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
                                  col("size"): pick("size", str), col("strategies"): pick("strategies"),
                                  col("rules"): pick("rules", lambda v: v or "—"), col("commit"): pick("commit"), "hash": pick("hash")})
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
    kind = st.radio(t("tr.model"), ["train_lgbm", "train_mlp"], format_func=lambda k: kind_text()[k], horizontal=True, key="pld-kind")
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
        table = pl_select(t("match.opponent"), list(match_tables()), "pld-table", default="default", format_func=match_tables().get)
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
        clicked = cols[0].button(add_label, key=f"pl-btn-add-{kind}", type="primary", on_click=pl_dialog_reset, width="stretch")  # blue like the other main buttons
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
        args = {"kind": kind_text()[tr["kind"]], "name": tr["name"] + tr["ext"]}
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
        # the name may stay empty (one click less for a single item): the default is used then
        # (a fixed label: a label that changes with the items would make Streamlit forget what was typed)
        typed = pl_text(t("pl.run.name"), "pl-run-name", "", "auto")
        if not typed:
            st.caption(t("pl.run.name_auto", name=default_name))
        pipe_name = typed or default_name
        problems = []
        for plan in [*datas, *trains, *matches]:
            for p_ in plan["problems"]:
                if p_ not in problems:
                    problems.append(p_)
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
        if action_row(t("pl.run.start_one") if len(steps) == 1 else t("pl.run.start"), "pl-btn-start", problems):
            try:
                pl_write_configs(players, datas, matches)
                ids = jobs.start_pipeline(pipe_name, steps)
            except (OSError, ValueError, TimeoutError) as e:
                st.error(str(e))
            else:
                st.session_state["job-select"] = ids[0]
                st.session_state["job-started"] = t("pl.run.started", name=pipe_name, n=len(ids))
                pl_new_players()   # the pipeline is queued: the form starts empty again (a template or the jobs page has what was run)
                for k in ("pl-run-name", "pl-run-name-for"):
                    st.session_state.pop(k, None)
                pl_persist()
                st.rerun()


def pipeline_page():
    pl_restore()
    pl_take_prefill()
    st.caption(t("pl.intro"))
    players = st.radio(t("match.players"), [4, 3], horizontal=True, format_func=lambda n: t("match.players_n", n=n), key="pl-players", on_change=pl_new_players)
    pl_template_card()
    datas, trains, matches = pl_plans(players)
    pl_data_card(players, datas)
    pl_train_card(players, trains)
    pl_match_card(players, matches, trains)
    pl_run_card(players, datas, trains, matches)
    pl_persist()
