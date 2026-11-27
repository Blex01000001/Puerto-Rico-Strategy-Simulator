"""Pages hash 說明 (id hash) and 版本控管 (id versions)."""

import os
import re

import streamlit as st
import pandas as pd

import fingerprint

from mlui.text import (  # noqa: F401
    lang,
    t,
)
from mlui.common import (  # noqa: F401
    PARAM_DEFAULTS,
    _esc,
    card,
    list_dumps,
    model_files,
    model_meta,
    version_table,
    version_tiles,
)


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


def versions_page():
    tracks, error = fingerprint.load_versions(lang=lang())
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
