"""Page 模型訓練/蒸餾 (id train): train a LightGBM or MLP value model."""

import datetime
import os

import streamlit as st
import pandas as pd

import fingerprint
import train_options

from mlui.text import (  # noqa: F401
    lang,
    t,
)
from mlui.common import (  # noqa: F401
    LOCAL_MODELS,
    MODELS_DIR,
    action_row,
    card,
    delete_gen,
    dump_column_config,
    filter_bar,
    folder_line,
    grid,
    kind_text,
    list_dumps,
    model_files,
    model_meta,
    param_inputs,
    pending_output,
    reader_problem,
    rel,
    same_name_notice,
    start_job,
    table_view,
)


PARAM_DOC_ROWS = {"train_lgbm": 8, "train_mlp": 8, "common": 2}  # rows per section of the parameter guide (texts: pdoc.<section>.<row>.<column>)


def param_doc(kind):
    """The parameter guide rows of a model kind plus the shared ones, in the active language."""
    rows = []
    for section in (kind, "common"):
        rows += [tuple(t(f"pdoc.{section}.{i}.{j}") for j in range(6)) for i in range(PARAM_DOC_ROWS[section])]
    return rows


def training_tab():
    dumps = list_dumps()
    bad = [d for d in dumps if "error" in d]
    writing = [d for d in dumps if d.get("writing")]
    good = [d for d in dumps if "error" not in d and not d.get("writing")]
    with card("train-data", t("tr.card1")):
        if not good:
            for d in writing:
                st.info(t("tr.writing", path=d["path"], mb=d["大小 MB"]))
            st.info(t("tr.no_data", page=t("page.data")))
            return
        players = sorted({d["人數"] for d in good})
        p = st.radio(t("tr.players"), players, index=len(players) - 1, horizontal=True, format_func=lambda n: t("match.players_n", n=n))
        rows = [d for d in good if d["人數"] == p]
        feature_opts = sorted({d["特徵版本"] for d in rows})
        rules_opts = sorted({d["規則版本"] for d in rows if "規則版本" in d})
        fv, rv = filter_bar("train", [(t("dump.col.feature"), feature_opts, f"tf-feature-{p}", lambda n: f"v{n}"),
                                      (t("dump.col.rules"), rules_opts, f"tf-rules-{p}", None)])
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
            st.caption(t("tr.pick_hint", page=t("page.datamanage")))

    with card("train-model", t("tr.card2")):
        kind = st.radio(t("tr.model"), ["train_lgbm", "train_mlp"], format_func=lambda k: kind_text()[k], horizontal=True)
        defaults = train_options.defaults(kind)
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
            backend, device = train_options.resolve_backend(opts)
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
            start_job(kind, f"{kind_text()[kind]} → {name + ext}", spec)

    with card("train-doc", t("tr.card_doc"), t("tr.doc_sub")):
        cols = [t(f"pdoc.col.{j}") for j in range(6)]
        st.table(pd.DataFrame(param_doc(kind), columns=cols).set_index(cols[0]))
