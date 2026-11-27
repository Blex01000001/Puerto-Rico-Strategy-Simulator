"""Page AI 分析 (id analysis): chat with an LLM about models and data (ml/llm.py)."""

import datetime
import os

import streamlit as st

import llm
import modelmeta

from mlui.text import (  # noqa: F401
    t,
)
from mlui.common import (  # noqa: F401
    card,
    list_dumps,
    model_files,
    model_meta,
    model_path,
    model_stale,
    models_using,
    plain,
)


def ai_save_provider(name):
    settings = llm.load_settings()
    ps = settings["providers"][name]
    ps["model"] = (st.session_state.get(f"ai-{name}-model-in") or ps["model"]).strip() or llm.PROVIDERS[name]["model"]
    try:
        ps["conversationLimit"] = max(2000, int(st.session_state.get(f"ai-{name}-limit-in") or ps["conversationLimit"]))
    except (TypeError, ValueError):
        pass
    llm.save_settings(settings)
    st.session_state["job-started"] = t("ai.saved")


def ai_set_enabled(name):
    settings = llm.load_settings()
    settings["providers"][name]["enabled"] = bool(st.session_state.get(f"ai-{name}-enabled"))
    llm.save_settings(settings)


def ai_load_models(name):
    try:
        st.session_state[f"ai-{name}-models"] = llm.list_models(llm.provider_settings(llm.load_settings(), name))
        st.session_state.setdefault("ai-errors", {}).pop(name, None)
    except llm.LlmError as e:
        st.session_state.setdefault("ai-errors", {})[name] = str(e)


def ai_pick_model(name):
    st.session_state[f"ai-{name}-model-in"] = st.session_state.get(f"ai-{name}-model-pick") or st.session_state.get(f"ai-{name}-model-in")


def ai_save_primer():
    settings = llm.load_settings()
    settings["primer"] = st.session_state.get("ai-primer-in", "")
    llm.save_settings(settings)
    st.session_state["job-started"] = t("ai.saved")


def ai_reset_primer():
    st.session_state["ai-primer-in"] = llm.DEFAULT_PRIMER
    ai_save_primer()


def ai_question_use():
    settings = llm.load_settings()
    q = next((q for q in settings["questions"] if q["name"] == st.session_state.get("ai-q-pick")), None)
    if q:
        st.session_state["ai-question"] = q["text"]


def ai_question_delete():
    settings = llm.load_settings()
    settings["questions"] = [q for q in settings["questions"] if q["name"] != st.session_state.get("ai-q-pick")]
    llm.save_settings(settings)


def ai_question_add():
    name, text = (st.session_state.get("ai-q-name") or "").strip(), (st.session_state.get("ai-q-text") or "").strip()
    if not name or not text:
        return
    settings = llm.load_settings()
    settings["questions"] = [q for q in settings["questions"] if q["name"] != name] + [{"name": name, "text": text}]
    llm.save_settings(settings)
    st.session_state["ai-q-name"] = st.session_state["ai-q-text"] = ""


def ai_new_conversation():
    for k in ("ai-histories", "ai-items", "ai-errors", "ai-pending", "ai-last-question"):
        st.session_state.pop(k, None)


def ai_targets(settings):
    """The providers that will get the next question: enabled and with a key found."""
    return [n for n in llm.PROVIDERS if settings["providers"][n]["enabled"] and llm.api_key(llm.provider_settings(settings, n))[0]]


def ai_send(digests, labels, only=None):
    """Callback of the send button (only=None: every target) and of a tab's retry button (only=[provider])."""
    question = (st.session_state.get("ai-question") or "").strip() if only is None else st.session_state.get("ai-last-question", "")
    if not question:
        return
    st.session_state["ai-pending"] = {"question": question, "digests": digests, "labels": labels, "only": only}
    st.session_state["ai-last-question"] = question
    if only is None:
        st.session_state["ai-question"] = ""


def ai_process_pending(settings):
    """Sends the pending question to every target at once (one thread each; one provider failing does not stop the others). Each provider
    has its own history: a provider with none yet gets the first message (background + data + question), the others only the question.
    When nobody answers, the question goes back into the box."""
    pending = st.session_state.pop("ai-pending", None)
    if not pending:
        return
    histories = st.session_state.setdefault("ai-histories", {})
    errors = st.session_state.setdefault("ai-errors", {})
    names = [n for n in ai_targets(settings) if pending["only"] is None or n in pending["only"]]
    calls = {}
    for name in names:
        ps = llm.provider_settings(settings, name)
        history = histories.get(name, [])
        text = pending["question"] if history else llm.first_message(settings["primer"], pending["digests"], pending["question"])
        user = {"role": "user", "text": text}
        projected = llm.history_chars(history) + len(text)
        if projected > ps["conversationLimit"]:
            errors[name] = t("ai.p.limit", n=f"{projected:,}", limit=f"{ps['conversationLimit']:,}")
            continue
        errors.pop(name, None)
        calls[name] = (ps, history + [user], user)
    answered = False
    if calls:
        from concurrent.futures import ThreadPoolExecutor
        with st.spinner(t("ai.waiting", model=t("common.list").join(llm.PROVIDERS[n]["label"] for n in calls))):
            with ThreadPoolExecutor(max_workers=len(calls)) as pool:
                futures = {n: pool.submit(llm.chat, ps, llm.SYSTEM_INSTRUCTION, hist) for n, (ps, hist, _) in calls.items()}
                for name, future in futures.items():
                    ps, hist, user = calls[name]
                    try:
                        reply = future.result()
                    except llm.LlmError as e:
                        errors[name] = str(e)
                        continue
                    answered = True
                    histories.setdefault(name, []).extend([user, {"role": "model", "text": reply["text"], "model": ps["model"],
                                                                 "seconds": reply["seconds"], "tokens": reply["tokens"]}])
    if answered and not st.session_state.get("ai-items"):
        st.session_state["ai-items"] = pending["labels"]
    if not answered and pending["only"] is None:
        st.session_state["ai-question"] = pending["question"]


def ai_sources(locked):
    """The multiselects for what to analyse; returns (digest text, labels). Locked once a conversation started (the data is in the first message)."""
    models = [os.path.basename(p) for p in model_files()]
    dumps = {os.path.basename(d["path"]): d for d in list_dumps() if "_meta" in d}
    c1, c2 = st.columns(2)
    chosen_models = c1.multiselect(t("ai.models"), models, key="ai-sel-models", disabled=locked)
    chosen_dumps = c2.multiselect(t("ai.dumps"), list(dumps), key="ai-sel-dumps", disabled=locked)
    with_matches = st.checkbox(t("ai.with_matches"), value=True, key="ai-matches", disabled=locked)
    items = []
    for name in chosen_models:
        meta = model_meta(model_path(name))
        items.append(modelmeta.model_digest(name, meta, model_stale(meta), matches=with_matches) if meta else f"M {name} (no metadata)")
    for name in chosen_dumps:
        d = dumps[name]
        items.append(modelmeta.dump_digest(name, d["_meta"], d["hash"], d["規則版本"], models_using(d["path"]), d["大小 MB"], d["_stale"]))
    return (modelmeta.digest(items) if items else ""), chosen_models + chosen_dumps


def ai_provider_tab(settings, name):
    ps = llm.provider_settings(settings, name)
    key, source = llm.api_key(ps)
    env = llm.PROVIDERS[name]["env"]
    if key:
        st.markdown(f'<span class="act-note">{t("ai.key_ok", source=t("ai.key_src." + source, env=env))}</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="act-err">{t("ai.key_missing", env=env)}</span>', unsafe_allow_html=True)
    st.checkbox(t("ai.enabled"), value=ps["enabled"], key=f"ai-{name}-enabled", on_change=ai_set_enabled, args=(name,))
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    c1.text_input(t("ai.model"), value=ps["model"], key=f"ai-{name}-model-in")
    c2.number_input(t("ai.limit"), min_value=2000, step=10000, value=int(ps["conversationLimit"]), key=f"ai-{name}-limit-in")
    models = st.session_state.get(f"ai-{name}-models") or []
    d1, d2, d3 = st.columns([1.6, 1.6, 3.4], vertical_alignment="bottom")
    d1.button(t("ai.save"), key=f"ai-{name}-save", on_click=ai_save_provider, args=(name,), width="stretch")
    d2.button(t("ai.load_models"), key=f"ai-{name}-load", on_click=ai_load_models, args=(name,), disabled=not key, width="stretch")
    if models:
        d3.selectbox(t("ai.model_pick"), models, index=models.index(ps["model"]) if ps["model"] in models else 0,
                     key=f"ai-{name}-model-pick", on_change=ai_pick_model, args=(name,))
    if st.session_state.get("ai-errors", {}).get(name) and not st.session_state.get("ai-histories", {}).get(name):
        st.markdown(f'<span class="act-err">{plain(st.session_state["ai-errors"][name])}</span>', unsafe_allow_html=True)


def ai_settings_card(settings):
    names = list(llm.PROVIDERS)

    def title(n):
        key = llm.api_key(llm.provider_settings(settings, n))[0]
        return f"{llm.PROVIDERS[n]['label']}　{'✔' if key else '✘'}" + ("" if settings["providers"][n]["enabled"] else f"（{t('ai.off')}）")

    for tab, name in zip(st.tabs([title(n) for n in names]), names):
        with tab:
            ai_provider_tab(settings, name)
    st.caption(t("ai.privacy"))


def ai_primer_card(settings):
    st.text_area(t("ai.primer"), value=settings["primer"], height=190, key="ai-primer-in")
    a1, a2, _ = st.columns([1.4, 1.4, 4])
    a1.button(t("ai.primer_save"), key="ai-primer-save", on_click=ai_save_primer, width="stretch")
    a2.button(t("ai.primer_reset"), key="ai-primer-reset", on_click=ai_reset_primer, width="stretch")
    st.markdown(f"**{t('ai.questions')}**")
    names = [q["name"] for q in settings["questions"]]
    b1, b2, b3, _ = st.columns([2.4, 1.2, 1.2, 2.4], vertical_alignment="bottom")
    pick = b1.selectbox(t("ai.q_pick"), names, key="ai-q-pick") if names else None
    b2.button(t("ai.q_use"), key="ai-q-use", on_click=ai_question_use, disabled=not names, width="stretch")
    with b3:
        delete_row = st.container(key="del-ai-question")  # dangerous action: dark, red text (CSS del-)
        delete_row.button(t("ai.q_delete"), key="del-ai-question-btn", on_click=ai_question_delete, disabled=not names, width="stretch")
    if pick:
        st.caption(next(q["text"] for q in settings["questions"] if q["name"] == pick))
    n1, n2 = st.columns([1, 3], vertical_alignment="bottom")
    n1.text_input(t("ai.q_name"), key="ai-q-name")
    n2.text_input(t("ai.q_text"), key="ai-q-text")
    st.button(t("ai.q_add"), key="ai-q-add", on_click=ai_question_add)


def ai_conversation(name, settings, digests, labels):
    """One provider's conversation in its tab: the messages, its error (with a retry button) and nothing else."""
    history = st.session_state.get("ai-histories", {}).get(name, [])
    for m in history:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.markdown(llm.display_question(m["text"]) if m["role"] == "user" else m["text"])
            if m["role"] == "model":
                st.caption(t("ai.reply_info", model=m.get("model") or "?", sec=m.get("seconds"), tokens=m.get("tokens") or "—"))
    error = st.session_state.get("ai-errors", {}).get(name)
    if error:
        st.markdown(f'<span class="act-err">{plain(error)}</span>', unsafe_allow_html=True)
        if st.session_state.get("ai-last-question"):
            st.button(t("ai.retry"), key=f"ai-retry-{name}", on_click=ai_send, args=(digests, labels, [name]))
    elif not history:
        st.caption(t("ai.empty_conversation"))


def analysis_page():
    """Ask several LLMs (Gemini, Claude) the same question about training data and value models (their digests, no paths) and keep asking:
    every provider has its own conversation, shown side by side in tabs; each history is kept here and sent whole every time."""
    settings = llm.load_settings()
    ai_process_pending(settings)
    histories = st.session_state.get("ai-histories", {})
    started = any(histories.values())
    with card("ai-settings", t("ai.settings_card"), t("ai.settings_sub")):
        ai_settings_card(settings)
    with card("ai-primer", t("ai.primer_card"), t("ai.primer_sub")):
        ai_primer_card(settings)
    with card("ai-sources", t("ai.sources_card"), t("ai.sources_sub")):
        digests, labels = ai_sources(started)
        if started:
            st.caption(t("ai.locked", items=t("common.list").join(st.session_state.get("ai-items", [])) or "—"))
        elif digests:
            n, limit = len(digests), modelmeta.DIGEST_LIMIT
            st.markdown(f'<span class="{"act-err" if n > limit else "act-note"}">'
                        f'{t("digest.over", n=f"{n:,}", limit=f"{limit:,}") if n > limit else t("digest.count", n=f"{n:,}", limit=f"{limit:,}")}</span>',
                        unsafe_allow_html=True)
    with card("ai-chat", t("ai.chat_card")):
        targets = ai_targets(settings)
        shown = [n for n in llm.PROVIDERS if n in targets or histories.get(n)]
        if shown:
            for tab, name in zip(st.tabs([llm.PROVIDERS[n]["label"] for n in shown]), shown):
                with tab:
                    ai_conversation(name, settings, digests, labels)
        st.text_area(t("ai.question"), key="ai-question", height=110)
        question = (st.session_state.get("ai-question") or "").strip()
        problems, skipped = [], []
        if not targets:
            problems.append(t("ai.p.no_target"))
        if not question:
            problems.append(t("ai.p.question"))
        if targets and not any(histories.get(n) for n in targets) and not digests:
            problems.append(t("ai.p.sources"))
        first_len = len(settings["primer"]) + len(digests)
        for n in targets:  # a provider whose conversation would pass its limit is skipped (its tab says why); all of them over = nothing to send
            ps = llm.provider_settings(settings, n)
            if llm.history_chars(histories.get(n, [])) + len(question) + (0 if histories.get(n) else first_len) > ps["conversationLimit"]:
                skipped.append(ps["label"])
        if targets and len(skipped) == len(targets):
            problems.append(t("ai.p.limit_all", names=t("common.list").join(skipped)))
        with st.container(key="actionbar-ai-send"):
            c1, c2, c3, c4 = st.columns([1.6, 1.3, 1.6, 4], vertical_alignment="center")
            c1.button(t("ai.send", n=len(targets) - len(skipped)), key="ai-send", type="primary", disabled=bool(problems), on_click=ai_send,
                      args=(digests, labels), width="stretch")
            c2.button(t("ai.new"), key="ai-new", disabled=not started, on_click=ai_new_conversation, width="stretch")
            conversations = [{"label": llm.PROVIDERS[n]["label"], "history": histories[n]} for n in llm.PROVIDERS if histories.get(n)]
            c3.download_button(t("ai.export"), llm.export_markdown(st.session_state.get("ai-items", []), conversations),
                               file_name=f"ai-analysis-{datetime.date.today():%Y%m%d}.md", mime="text/markdown", disabled=not started, width="stretch")
            if problems:
                c4.markdown(f'<span class="act-err">{t("act.cannot", reasons=t("common.sep").join(plain(x) for x in problems))}</span>', unsafe_allow_html=True)
            else:
                names_text = t("common.list").join(llm.PROVIDERS[n]["label"] for n in targets if llm.PROVIDERS[n]["label"] not in skipped)
                note = t("ai.targets", names=names_text) + (t("ai.skipped", names=t("common.list").join(skipped)) if skipped else "")
                c4.markdown(f'<span class="act-note">{note}</span>', unsafe_allow_html=True)
