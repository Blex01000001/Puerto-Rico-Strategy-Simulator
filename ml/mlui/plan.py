"""What a pipeline item will do (plans): files, problems and details, computed without drawing widgets, so the page and the
dialogs use the same checks and tests can call them directly."""

import os

import streamlit as st

import pipeline_form
import fingerprint
import jobs
import train_options

from mlui.text import (  # noqa: F401
    t,
)
from mlui.common import (  # noqa: F401
    LOCAL_CONFIGS,
    LOCAL_MODELS,
    ROOT,
    absolute,
    all_strategies,
    kind_text,
    list_dumps,
    match_default_name,
    match_seats,
    model_name_taken,
    model_path,
    pending_output,
    read_config,
    rel,
    safe_name,
    selfplay_config,
)


FEATURE_COUNTS = {1: 430, 2: 512}   # features per feature version (the training page shows the real count of the data it is given)
ROWS_PER_GAME = {4: 2240, 3: 1600}  # rows a game gives per unit of sampling rate (about: decisions x seats); only for the estimates


def pl_rows(games, rate, players):
    return int(games * rate * ROWS_PER_GAME.get(players, 2000))


# ---- items


def pl_items(kind):
    """The items of a list: "d" data, "t" models to train, "m" matches."""
    return st.session_state.setdefault(pipeline_form.LISTS[kind], [])


# ---- what an item will do (plans: no widgets, so the page and the dialogs use the same checks)




def seat_orders():
    """The seat orders in the Dashboard's order (Engine SeatParams.SeatOrders, via ml/engine-info.json)."""
    return tuple(fingerprint.engine_info().get("seatOrders") or ("random", "balanced", "rotate", "fixed"))


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
    seat_order = item.get("seat_order") if item.get("seat_order") in seat_orders() else "random"
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
    return train_options.defaults(kind)


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
    plan["details"] = ([(t("pl.det.name"), name + ext, 1, 1, 3), (t("pl.det.kind"), kind_text()[kind], 1, 4, 1),
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
