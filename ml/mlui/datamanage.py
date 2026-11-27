"""Management page 訓練資料 (id datamanage): list, rename and delete training data."""

import os

import streamlit as st
import pandas as pd

import jobs
import modelmeta

from mlui.text import (  # noqa: F401
    t,
)
from mlui.common import (  # noqa: F401
    absolute,
    busy_files,
    card,
    delete_button,
    delete_gen,
    digest_box,
    dump_column_config,
    filter_bar,
    folder_line,
    grid,
    job_title,
    list_dumps,
    models_using,
    pending_readers,
    plain,
    table_view,
    version_tiles,
)


def rename_dump_dialog(d):
    st.dialog(t("dm.rn.title"))(_rename_dump_dialog)(d)


def _rename_dump_dialog(d):
    path = absolute(d["path"])
    name = os.path.basename(path)
    new = st.text_input(t("dm.rn.new"), value=name[:-4], key=f"dm-rename-new-{name}").strip()
    if new.endswith(".bin"):
        new = new[:-4]
    problems = []
    if not new or any(c in new for c in modelmeta.INVALID_NAME_CHARS):
        problems.append(t("md.rn.p.name"))
    elif new + ".bin" == name:
        problems.append(t("md.rn.p.same"))
    elif os.path.exists(os.path.join(os.path.dirname(path), new + ".bin")):
        problems.append(t("dm.rn.p.taken", name=new + ".bin"))
    busy = pending_readers(d["path"]) + ([job_title(j) for j in jobs.list_jobs() if j["state"] in ("waiting",) + jobs.BUSY
                                          and str(j.get("spec", {}).get("out", "")).replace("\\", "/") == d["path"]])
    if busy:
        problems.append(t("dm.rn.p.busy", title=busy[0]))
    st.caption(t("dm.rn.caption", name=name))
    refs = modelmeta.dump_references(path)
    if refs["local"]:
        st.info(t("dm.rn.refs", list="\n".join(f"- `{os.path.basename(p).removesuffix('.meta.json')}`" for p in refs["local"])))
    if refs["official"]:
        st.warning(t("dm.rn.official", list=t("common.list").join(f"`{os.path.basename(p).removesuffix('.meta.json')}`" for p in refs["official"])))
    if problems:
        st.markdown(f'<span class="act-err">{t("md.rn.cannot", reasons=t("common.sep").join(plain(x) for x in problems))}</span>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button(t("queue.cancel"), key=f"dm-rename-cancel-{name}", width="stretch"):
        st.rerun()
    if c2.button(t("md.rn.ok"), type="primary", key=f"dm-rename-ok-{name}", width="stretch", disabled=bool(problems)):
        try:
            target = modelmeta.rename_dump(path, new)
            st.session_state["job-started"] = t("md.rn.done", name=name, new=os.path.basename(target))
            st.session_state["del-gen"] = delete_gen() + 1  # the table rows are renumbered: drop the selection
            st.cache_data.clear()
            st.rerun()
        except ValueError as e:
            st.error(str(e))


def dump_detail(d):
    """What one training data file is: sizes, versions, the seats that played it, the models trained on it."""
    meta = d["_meta"]
    st.markdown(version_tiles([(t("dump.col.players"), str(d["人數"])), (t("dump.col.games"), f"{d['局數']:,}"), (t("dump.col.rows"), f"{d['列數']:,}"),
                               (t("dump.col.rate"), f"{d['抽樣率']:g}"), (t("dump.col.feature"), str(d["特徵版本"])),
                               (t("dump.col.size"), f"{d['大小 MB']:g}")], centre=True), unsafe_allow_html=True)
    st.caption(t("dm.d.foot", rules=d["規則版本"], hash=d["hash"], commit=(d.get("引擎 commit") or "—")[:7], engine=meta.get("engineVersion") or "—",
                 seed=meta.get("seed"), order=meta.get("seatOrder"), status=d["狀態"]))
    seats = pd.DataFrame([{t("dm.d.col.seat"): s_.get("id", i), t("dm.d.col.strategy"): s_.get("strategy"),
                           t("dm.d.col.params"): ", ".join(f"{k}={v}" for k, v in (s_.get("params") or {}).items()) or "—"}
                          for i, s_ in enumerate(meta.get("seats", []))])
    st.markdown(t("dm.d.seats"))
    grid(seats, hide_index=True, width="stretch")
    users = models_using(d["path"])
    st.markdown(t("dm.d.used_by"))
    st.caption(t("common.list").join(f"`{u}`" for u in users) if users else t("dm.d.not_used"))
    if d.get("_stale"):
        st.warning(t("dm.d.stale", notes=t("common.sep").join(d["_stale"])))
    folder_line(os.path.dirname(d["path"]) + "/", f"dm-folder-{d['path']}")


def data_manage_page():
    """Training data: the list (quick filters, tick rows), rename / delete / copy-for-AI on the ticked rows, and the details of one.
    Deleting and renaming training data happens here only."""
    dumps = list_dumps()
    good = [d for d in dumps if "error" not in d and not d.get("writing")]
    with card("dm-list", t("dm.card"), t("dm.card_sub", train=t("page.train"))):
        for d in (x for x in dumps if x.get("writing")):
            st.info(t("tr.writing_wait", path=d["path"], mb=d["大小 MB"]))
        if not good:
            st.caption(t("dm.none", page=t("page.data")))
            chosen = []
        else:
            chosen = dump_list(good)
    with card("dm-detail", t("dm.detail")):
        if len(chosen) == 1:
            dump_detail(chosen[0])
        else:
            st.caption(t("dm.select_hint"))


def dump_list(good):
    players_opts = sorted({str(d["人數"]) for d in good})
    feature_opts = sorted({d["特徵版本"] for d in good})
    rules_opts = sorted({d["規則版本"] for d in good if "規則版本" in d})
    pl, fv, rv = filter_bar("dm", [(t("dump.col.players"), players_opts, "dm-players", lambda n: t("match.players_n", n=n)),
                                   (t("dump.col.feature"), feature_opts, "dm-feature", lambda n: f"v{n}"),
                                   (t("dump.col.rules"), rules_opts, "dm-rules", None)])
    rows = [d for d in good if str(d["人數"]) in (pl or players_opts) and d["特徵版本"] in (fv or feature_opts) and d.get("規則版本") in (rv or rules_opts)]
    if not rows:
        st.caption(t("mlist.none"))
        return []
    df = table_view(rows).set_index(pd.Index([os.path.basename(r["path"]) for r in rows], name=t("dump.col.file")))
    # a selection is by row number: the filters and the deletion counter are part of the key
    picked = grid(df, on_select="rerun", selection_mode="multi-row", width="stretch", column_config=dump_column_config(),
                  key=f"dumps-manage-{delete_gen()}-{'.'.join(pl or [])}-{'.'.join(map(str, fv or []))}-{'.'.join(rv or [])}")
    chosen = [rows[i] for i in picked.selection.rows]
    st.caption(t("dm.footer", shown=len(rows), total=len(good)))
    items = [modelmeta.dump_digest(os.path.basename(d["path"]), d["_meta"], d["hash"], d["規則版本"], models_using(d["path"]), d["大小 MB"], d["_stale"])
             for d in chosen]
    # the action bar: rename (exactly one ticked) | copy details | hint ........ delete
    with st.container(key="actionbar-dumps"):
        c_rename, c_copy, c_hint, c_delete = st.columns([1.2, 1.9, 4.2, 1.7], vertical_alignment="center")
        if c_rename.button(t("md.rename"), key="dm-rename", width="stretch", disabled=len(chosen) != 1):
            rename_dump_dialog(chosen[0])
        hint = digest_box(modelmeta.digest(items) if chosen else "", "dumps", len(chosen), c_copy)
        if hint:
            c_hint.markdown(hint, unsafe_allow_html=True)
        with c_delete:
            delete_button("del-dumps", t("del.button", n=len(chosen)), [absolute(d["path"]) for d in chosen], extra_suffixes=(".json",), busy=busy_files("data"))
    st.caption(t("dm.actions_hint") + " " + t("dt.delete_hint", page=t("page.train")))
    return chosen
