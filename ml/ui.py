"""ML UI: generate data, train value models, run matches and browse them (Streamlit).

    streamlit run ml/ui.py --server.address localhost      (or ml/start-ui.sh / ml\\start-ui.cmd)

This file is only the entry: the language check, the navigation and main(). Every page is a module of ml/mlui/
(data, train, match, pipeline + plan, datamanage, models, analysis, jobqueue, helppages); what two or more pages use is in
mlui/common.py, the CSS in mlui/style.py, lang()/t() in mlui/text.py. Streamlit re-runs this file on every interaction;
the mlui modules are imported once, so nothing in them may compute a translated text when it is imported (texts are
built inside functions: t() reads the language of the current run).
Jobs run in their own process (jobs.py): closing this page or the UI does not stop them.
Reads the same folders as the Dashboard: results/ (PR_RESULTS_DIR overrides) and ml/models/.
"""
import streamlit as st

import check_env
from mlui.text import lang, t

if check_env.missing_modules():
    # started with a Python that lacks the packages (e.g. pip installed them into another Python): say so plainly
    st.set_page_config(page_title="Puerto Rico Machine Learning", page_icon="🌱")
    st.error(t("missing.error", names=", ".join(check_env.missing_modules())))
    st.markdown(t("missing.python", python=check_env.sys.executable))
    st.markdown(t("missing.fix"))
    st.code(check_env.fix_command(), language=None)
    st.caption(t("missing.note"))
    st.stop()

from mlui.analysis import analysis_page  # noqa: E402
from mlui.common import DASHBOARD_URL, TITLE, sidebar_status  # noqa: E402
from mlui.data import data_tab  # noqa: E402
from mlui.datamanage import data_manage_page  # noqa: E402
from mlui.helppages import hash_page, versions_page  # noqa: E402
from mlui.jobqueue import queue_page  # noqa: E402
from mlui.match import match_tab  # noqa: E402
from mlui.models import models_page  # noqa: E402
from mlui.pipeline import pipeline_page  # noqa: E402
from mlui.style import CSS  # noqa: E402
from mlui.train import training_tab  # noqa: E402


def pages():
    return [("data", t("page.data"), "🎲", lambda: data_tab(), t("section.flow")),
         ("train", t("page.train"), "🧠", lambda: training_tab(), None),
         ("match", t("page.match"), "⚔️", lambda: match_tab(), None),
         ("pipeline", t("page.pipeline"), "🔗", lambda: pipeline_page(), None),
         ("datamanage", t("page.datamanage"), "🗃️", lambda: data_manage_page(), t("section.manage")),
         ("models", t("page.models"), "📦", lambda: models_page(), None),
         ("analysis", t("page.analysis"), "🤖", lambda: analysis_page(), None),
         ("queue", t("page.queue"), "🗂️", lambda: queue_page(), None),
         ("hash", t("page.hash"), "🔑", lambda: hash_page(), t("section.help")),
         ("versions", t("page.versions"), "🏷️", lambda: versions_page(), None)]


def current_page():
    ids = [p[0] for p in pages()]
    page = st.session_state.get("page") or st.query_params.get("page")
    page = {"modellist": "models"}.get(page, page)  # the model list and the model details are one page now
    return page if page in ids else ids[0]


SCROLL_TOP_PAGE = """<!doctype html><script>
function up() {
  const d = window.parent.document;
  for (const sel of ['[data-testid="stMain"]', 'section.main', '[data-testid="stAppViewContainer"]']) {
    const e = d.querySelector(sel); if (e) e.scrollTo(0, 0);
  }
  window.parent.scrollTo(0, 0);
}
up(); setTimeout(up, 150);
</script>"""


def scroll_to_top():
    """Streamlit keeps the scroll position when another page is drawn: a tiny invisible iframe scrolls the main area to the top."""
    with st.container(key="scrolltop"):  # zero-size (CSS)
        if hasattr(st, "iframe"):
            st.iframe(SCROLL_TOP_PAGE, height=1)
        else:
            import streamlit.components.v1 as components
            components.html(SCROLL_TOP_PAGE, height=0)


def go(page):
    if page != st.session_state.get("page"):
        st.session_state["scroll-top"] = True  # the next run draws the new page: start it at the top
    st.session_state["page"] = page
    st.query_params["page"] = page  # a reload stays on the same page


def switch_language():
    other = "zh-TW" if lang() == "en" else "en"
    st.session_state["lang"] = other
    st.query_params["lang"] = other


def sidebar_nav(page):
    st.markdown(f'<div class="nav-brand"><span class="nav-icon">🌱</span><span>Puerto Rico<br>Machine Learning</span></div>',
                unsafe_allow_html=True)
    for pid, title, icon, _, section in pages():
        if section:
            st.markdown(f'<div class="navsec">{section}</div>', unsafe_allow_html=True)
        # the active entry gets another key prefix (navon-) so the CSS can highlight it
        st.button(f"{icon} {title}", key=f"{'navon' if pid == page else 'nav'}-{pid}", width="stretch",
                  on_click=go, args=(pid,))
    st.button(t("lang.switch"), key="lang-toggle", on_click=switch_language)


def main():
    st.set_page_config(page_title=TITLE, page_icon="🌱", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    page = current_page()
    with st.sidebar:
        sidebar_nav(page)
        with st.container(key="side-status"):  # pinned to the bottom of the navigation (CSS)
            sidebar_status()
    st.title(t(f"page.{page}"))
    st.caption(t("header.flow", data=t("page.data"), train=t("page.train"), match=t("page.match"), url=DASHBOARD_URL))
    started = st.session_state.pop("job-started", None)
    if started:
        st.toast(started)
    scroll = st.session_state.pop("scroll-top", False)
    next(p for p in pages() if p[0] == page)[3]()
    if scroll:
        scroll_to_top()  # after the page: an invisible element before the title would push it down


main()
