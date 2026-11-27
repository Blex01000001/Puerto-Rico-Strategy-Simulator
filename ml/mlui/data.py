"""Page 模擬對局採樣 (id data): generate training data (Runner --dump-positions)."""

import datetime
import os
import re

import streamlit as st
import pandas as pd

import i18n
import fingerprint
import jobs

from mlui.text import (  # noqa: F401
    lang,
    t,
)
from mlui.common import (  # noqa: F401
    DEFAULT_CUSTOM,
    LOCAL_CONFIGS,
    ROOT,
    absolute,
    action_row,
    all_strategies,
    busy_files,
    card,
    config_rows,
    delete_button,
    delete_gen,
    folder_line,
    grid,
    list_dumps,
    model_path,
    models_for,
    models_using,
    pending_output,
    plain,
    read_config,
    reader_problem,
    rel,
    safe_name,
    same_name_notice,
    selfplay_config,
    start_job,
    tracked_by_git,
    write_config,
)


def strategy_text(name):
    """The short description of a strategy (i18n strategy.<name>), or None when there is none."""
    key = f"strategy.{name}"
    return t(key) if key in i18n.table(lang()) or key in i18n.table(i18n.DEFAULT) else None


def strategy_label(name):
    text = strategy_text(name)
    return name if not text else f"{name}（{text}）" if lang() == "zh-TW" else f"{name} ({text})"


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


def custom_seats(players):
    """One row per seat: strategy + its parameters. Returns (seats for the config, problems)."""
    names = all_strategies()
    seats, problems = [], []
    model_names = [t("custom.model_none")] + [os.path.basename(p) for p in models_for(players)]
    for i in range(players):
        default = DEFAULT_CUSTOM[players][i] if DEFAULT_CUSTOM[players][i] in names else names[0]
        c1, c2 = st.columns([2, 5])
        strat = c1.selectbox(t("custom.seat", n=i + 1), names, index=names.index(default), key=f"cu-s{i}",
                             format_func=strategy_label)
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
    tracked = tracked_by_git(chosen) if chosen else set()
    with st.container(key="actionbar-configs"):  # the hint on the left, the dangerous action on the right
        c1, c2 = st.columns([4, 2.2], vertical_alignment="center")
        c1.caption(t("cfg.hint") + (("" if lang() == "zh-TW" else " ") + t("cfg.tracked", n=len(tracked)) if tracked else ""))
        with c2:
            delete_button("del-configs", t("del.button", n=len(chosen)), [absolute(c) for c in chosen], busy=busy_files("config"))


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

    st.caption(t("dt.manage_hint", page=t("page.datamanage")))
