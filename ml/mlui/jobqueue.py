"""Page 排程佇列 (id queue): the job queue and job details."""

import datetime
import os
import time

import streamlit as st
import pandas as pd

import jobs
import modelmeta
import positions

from mlui.text import (  # noqa: F401
    t,
)
from mlui.common import (  # noqa: F401
    absolute,
    card,
    copy_button,
    grid,
    job_title,
    kind_text,
    loss_chart,
    plain,
    progress_of,
    rel,
    scrub,
)


def state_text():
    return {"waiting": "Queued", "queued": "Starting", "running": "Running", "done": "Done", "failed": "Failed", "cancelled": "Cancelled",
              "interrupted": t("job.state.interrupted"), "lost": t("job.state.lost")}


def confirm_cancel_pipeline(pid, name, done, total):
    st.dialog(t("queue.cancel_pipeline"))(_confirm_cancel_pipeline)(pid, name, done, total)


def _confirm_cancel_pipeline(pid, name, done, total):
    """Asks before cancelling a whole pipeline (the running job is stopped, the waiting ones are dropped); tells afterwards with a toast."""
    st.markdown(t("queue.cancel_pl_ask", name=name, done=done, total=total))
    c1, c2 = st.columns(2)
    if c1.button(t("queue.cancel_pl_keep"), key=f"keep-pl-{pid}", width="stretch"):
        st.rerun()
    if c2.button(t("queue.cancel_pl_ok"), key=f"del-plcancel-{pid}-confirm", width="stretch"):   # del-…-confirm: the solid red button
        jobs.cancel_pipeline(pid)
        st.session_state["job-started"] = t("queue.cancel_pl_done", name=name)
        st.rerun(scope="app")


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


def eta_text(job, evs):
    """'About N min left' (to the minute; 'at most' for training, which can stop early), or '' when unknown."""
    left = jobs.eta_seconds(evs, time.time())
    if left is None:
        return ""
    minutes = int(left // 60) + (1 if left % 60 else 0)
    if minutes < 1:
        span = t("eta.lt1")
    elif minutes < 60:
        span = t("eta.min", m=minutes)
    else:
        span = t("eta.hm", h=minutes // 60, m=minutes % 60)
    return t("eta.max", time=span) if job["kind"].startswith("train") else t("eta.left", time=span)


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
                confirm_cancel_pipeline(pid, p["name"], done_n, p["total"])
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
            cols[0].markdown(f"{plain(job_title(job))}  \n<span class='act-note'>{kind_text().get(job['kind'], job['kind'])}・{(job.get('created') or '').replace('T', ' ').rstrip('Z')} UTC{plain(pipe_text)}</span>",
                             unsafe_allow_html=True)
            text, color = QUEUE_STATE.get(job["state"], (job["state"], "#8892a2"))
            cols[1].markdown(f"<div style='text-align:center;color:{color};font-weight:600'>{text}</div>", unsafe_allow_html=True)
            running_evs = jobs.events(job["id"]) if job["state"] in ("queued", "running") else []
            eta = eta_text(job, running_evs) if job["state"] == "running" else ""
            cols[2].markdown(elapsed_text(job) + (f"  \n<span class='act-note'>{eta}</span>" if eta else ""), unsafe_allow_html=True)
            if job["state"] in ("queued", "running"):
                frac, ptext = progress_of(job, running_evs)
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
            st.progress(frac, text=f"{state_text().get(state, state)}：{text}")
        elif state in ("queued", "running"):
            st.info(text)
        steps = [e for e in evs if e["stage"] in ("iteration", "epoch")]
        if steps:
            train_loss = [e.get("trainLoss") for e in steps]
            st.altair_chart(loss_chart([e["validLoss"] for e in steps], [e.get("iteration") or e.get("epoch") for e in steps], height=220,
                                       train=train_loss if all(v is not None for v in train_loss) else None), width="stretch")
    with right:
        st.markdown(f"**{t('detail.kind')}**: {kind_text().get(job['kind'], job['kind'])}")
        st.markdown(f"**{t('detail.state')}**: {state_text().get(state, state)}")
        loaded = next((e for e in evs if e["stage"] == "loaded"), None)
        if loaded:
            st.markdown(f"**{t('detail.data')}**: " + t("detail.data_val", rows=f"{loaded['rows']:,}", valid=f"{loaded['validRows']:,}"))
        if job.get("started"):
            st.markdown(f"**{t('detail.start')}**: {job['started']}")
        if job.get("finished"):
            st.markdown(f"**{t('detail.end')}**: {job['finished']}")
        if state == "lost":
            st.warning(t("job.lost_help"))
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
        st.success(t("detail.model_saved", path=rel(result["model"]), match=t("page.match")))
    if job["kind"] == "dump" and state in ("done", "cancelled") and result.get("rows"):
        st.success(t("detail.dump_result", status=t("detail.dump_cancelled" if state == "cancelled" else "detail.dump_done"), games=f"{result['games']:,}",
                     rows=f"{result['rows']:,}", path=rel(result["output"]), train=t("page.train")))
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
