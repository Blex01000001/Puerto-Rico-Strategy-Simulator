"""The ML UI's CSS (same palette as the Dashboard: Dashboard/wwwroot/app.css; base theme in .streamlit/config.toml)."""


# Same palette as the Dashboard (Dashboard/wwwroot/app.css); the base theme is in .streamlit/config.toml.
CSS = """
<style>
/* Streamlit's top toolbar is a 60px bar floating over the page (menu on the right, the re-open button of a collapsed sidebar on the
   left). The page title lives in that bar: it is the first thing in the content and exactly as tall as the bar, so nothing
   is lost under the toolbar and no extra padding is needed above it. The content's own left padding keeps it clear of the
   re-open button. If a Streamlit upgrade changes the bar height, change --bar-h to match. */
:root { --bar-h: 60px; }
.block-container { padding-top: 0 !important; padding-bottom: 2rem !important; }
[data-testid="stHeader"] { background: transparent !important; }
/* the <style> block itself sits in an (empty) element container: its 1rem row gap would push the title below the bar */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) { display: none !important; }
[data-testid="stHeading"], [data-testid="stHeading"] h1 { margin: 0 !important; padding: 0 !important; }
[data-testid="stHeading"] { height: var(--bar-h); display: flex; align-items: center; }
[data-testid="stHeading"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }  /* Streamlit gives headings -1rem here: it would shift the centring */
[data-testid="stHeading"] h1 { font-size: 1.5rem !important; line-height: 1.2 !important; }
/* the lines under the title (flow caption, page intro) sit one line apart: the title bar keeps its 60px for the toolbar, so pull the next
   element up into it, and shrink the 1rem row gap after top-level captions / paragraphs (the ones inside cards are not touched) */
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(> [data-testid="stHeading"]) { margin-bottom: -1.3rem; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(> [data-testid="stCaptionContainer"]),
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"]) { margin-bottom: -.55rem; }
/* narrow window: the sidebar starts collapsed and the content only has 1rem of left padding, so the re-open button would sit on the title */
@media (max-width: 768px) { [data-testid="stHeading"] { padding-left: 2.75rem !important; } }
/* the « button shares the brand row (🌱 Puerto Rico ...) instead of having a row of its own above it */
[data-testid="stSidebarHeader"] { position: absolute !important; top: .85rem; right: .7rem; width: auto !important; height: auto !important; min-height: 0 !important;
  padding: 0 !important; margin: 0 !important; z-index: 3; }
[data-testid="stSidebarHeader"] [data-testid="stLogoSpacer"] { display: none !important; }
[data-testid="stSidebarUserContent"] { padding-top: .7rem !important; }
/* cards: st.container(border=True, key="card-...") */
div[class*="st-key-card-"] { background: #1f2430; border: 1px solid #333a4b !important; border-radius: 6px; padding: .55rem 1rem .8rem 1rem; }
.card-head { display: flex; align-items: baseline; gap: .9rem; margin-bottom: .2rem; }
.card-head h3 { flex: none; }
.card-head .card-sub { flex: 1 1 0; min-width: 0; font-size: .82rem; line-height: 1.35; color: #8892a2; }  /* long text wraps beside the title, never under it */
div[class*="st-key-card-"] h3 { font-size: 1.05rem; margin: .1rem 0 .2rem 0; padding: 0; border-left: 3px solid #4aa8ff; padding-left: .55rem; }
/* inputs like the Dashboard: darker than the card behind them, with a border (the theme's input colour equals the card
   colour). Streamlit >= 1.6x renders inputs with react-aria (data-testid / react-aria-* classes), older versions with
   baseweb (data-baseweb): both are listed so the borders survive either version. */
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"],
.react-aria-ComboBox > div, [data-testid="stMultiSelect"] .react-aria-ComboBox > div,
div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div {
  background: #111418 !important; border: 1px solid #333a4b !important; border-radius: 4px !important; }
[data-testid="stTextInputRootElement"] input, [data-testid="stNumberInputContainer"] input, .react-aria-ComboBox input,
div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea, textarea { background: transparent !important; }
[data-testid="stNumberInputContainer"] div[data-baseweb="input"], [data-testid="stNumberInputContainer"] [data-testid="stTextInputRootElement"] { border: 0 !important; }
[data-testid="stNumberInputContainer"] button { background: #1f2430 !important; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
.react-aria-ComboBox > div:focus-within, div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"] > div:focus-within { border-color: #4aa8ff !important; }
/* radio groups (人數, 模型, 對手…) get the same frame, sized to their options */
[data-testid="stRadioGroup"], div[role="radiogroup"] { display: inline-flex !important; width: auto !important; background: #111418;
  border: 1px solid #333a4b; border-radius: 4px; padding: .35rem .8rem; }
/* metrics (模型詳細資料: 種類, 資料列數, R², 最佳勝率) as framed tiles */
[data-testid="stMetric"] { background: #111418; border: 1px solid #333a4b; border-radius: 4px; padding: .45rem .8rem; }
[data-testid="stMetricValue"] > div { font-size: 1.7rem !important; }
/* delete buttons: red, at the right edge (delete_button wraps them in st.container(key="del-…")) */
div[class*="st-key-folderline-"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .5rem !important; align-items: center; }
div[class*="st-key-folderline-"] [data-testid="stColumn"] { flex: 0 1 auto !important; width: auto !important; min-width: 0 !important; }
div[class*="st-key-folderline-"] { margin: -.35rem 0 .35rem; }
.folder-path { font-size: .74rem; color: #8892a2; overflow-wrap: anywhere; }
div[class*="st-key-folderline-"] button { background: transparent !important; border: 0 !important; padding: 0 !important; min-height: 0 !important; height: auto !important; color: #4aa8ff !important; }
div[class*="st-key-folderline-"] button p { font-size: .74rem !important; text-decoration: underline; }
/* ONE button look in the whole UI (the one of the management action bars): secondary = dark with a grey frame, primary = blue (white text),
   dangerous (key prefix del- / stop-) = dark with red text; only the confirmation inside a delete dialog is solid red */
button[kind="secondary"] { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; border-radius: 6px; font-size: 13px; font-weight: 400;
  min-height: 0; padding: 6px 12px; }
button[kind="secondary"]:hover:not(:disabled) { border-color: #8b949e; color: #f0f6fc; }
button[kind="secondary"]:disabled { opacity: .45; cursor: not-allowed; }
button[kind="primary"] { background: #1f6feb !important; border: 1px solid rgba(240,246,252,.1) !important; color: #fff !important; border-radius: 6px;
  font-size: 13px; font-weight: 500 !important; min-height: 0; padding: 6px 14px; }
button[kind="primary"]:hover:not(:disabled) { filter: brightness(1.12); }
button[kind="primary"]:disabled { opacity: .4; cursor: not-allowed !important; }
/* the button that starts a whole pipeline is green (the other start buttons are blue) */
.st-key-pl-btn-start button[kind="primary"] { background: #238636 !important; }
div[class*="st-key-del-"] { align-items: flex-end !important; }
div[class*="st-key-del-"] [data-testid="stPopover"] { width: auto !important; }
div[class*="st-key-del-"]:not([class*="-confirm"]) button, div[class*="st-key-stop-"] button { color: #f85149 !important; }
div[class*="st-key-del-"][class*="-confirm"] button { background: #c43c3c !important; border: 0 !important; color: #fff !important; font-weight: 600 !important; }
/* the cancel button under the narrow navigation: smaller text and padding, never cut off with an ellipsis (both languages) */
div[class*="st-key-stop-side-"] button { padding: .25rem .3rem !important; min-height: 0 !important; font-size: .78rem !important; }
div[class*="st-key-stop-side-"] button p { white-space: nowrap !important; overflow: visible !important; text-overflow: clip !important; font-size: .78rem !important; }
.pl-detail { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: .6rem 1.1rem; padding: .45rem .3rem .55rem .75rem; }
.pl-detail .c { display: flex; flex-direction: column; min-width: 0; }
.pl-detail .k { color: #8892a2; font-size: .78rem; line-height: 1.3; }
.pl-detail .v { color: #eef1f5; font-size: .95rem; overflow-wrap: anywhere; }
.pl-rowtitle { font-size: 1.2rem; font-weight: 700; color: #eef1f5; padding-left: .55rem; border-left: 3px solid #4aa8ff; line-height: 1.3; }
div[class*="st-key-pl-seatcard"] { background: #1d2433; border: 1px solid #2b3447; border-radius: 4px; padding: .55rem .7rem; }
div[class*="st-key-pl-seatcard"] > div[data-testid="stVerticalBlock"], div[class*="st-key-pl-seatcard"] div[data-testid="stVerticalBlock"] { gap: .3rem; }
div[class*="st-key-pl-seatcard"] [data-testid="stWidgetLabel"] { min-height: 0; margin-bottom: .1rem; }
div[class*="st-key-pl-seatcard"] [data-testid="stWidgetLabel"] p { font-size: .8rem; font-weight: 600; color: #aab3c5; line-height: 1.2; }
div[class*="st-key-pl-seatcard"] [data-testid="stTextInputRootElement"], div[class*="st-key-pl-seatcard"] div[data-baseweb="select"] > div,
div[class*="st-key-pl-seatcard"] .react-aria-ComboBox { height: 2rem; min-height: 2rem; }
div[class*="st-key-pl-seatcard"] input { padding: .2rem .5rem; height: 100%; min-height: 0; font-size: .9rem; }
div[class*="st-key-pl-seatcard"] div[data-baseweb="select"] > div { padding-top: 0; padding-bottom: 0; }
div[class*="st-key-pl-addbox"] { border: 2px dashed #3a4258; border-radius: 8px; padding: .7rem .8rem; margin-top: .2rem; }
[data-testid="stPopover"] button, button[kind="primary"], button[kind="secondary"] { white-space: nowrap; }
.act-note { color: #8892a2; font-size: .82rem; line-height: 1.35; }
.act-err { color: #ec6a6a; font-size: .82rem; line-height: 1.35; }
.pl-problems { min-height: 2.4rem; font-size: .82rem; line-height: 1.35; margin: -.5rem 0 -.3rem; }
/* parameter grid: every label gets the height of two lines, so wrapped and unwrapped titles line up */
[class*="st-key-params"] [data-testid="stWidgetLabel"] { min-height: 2.6rem; display: flex; align-items: flex-end; }
/* sidebar: long job titles stay on one line and fade out */
.side-title { white-space: nowrap; overflow: hidden; color: #b4bcc9; font-size: .85rem;
  -webkit-mask-image: linear-gradient(to right, #000 78%, transparent); mask-image: linear-gradient(to right, #000 78%, transparent); }
.side-state { font-size: .85rem; }
.side-note { color: #8892a2; font-size: .78rem; margin: .1rem 0; }
/* version page: tiles and tables like the Dashboard's 版本控管 page (same look in both UIs) */
.vtiles { display: flex; flex-wrap: wrap; gap: .75rem; margin: .2rem 0 .6rem; }
/* the label takes its own line at the top (a long one wraps and pushes the value down), the value is centred in the rest */
.vtile { position: relative; flex: 1 1 9rem; min-height: 5.6rem; display: flex; flex-direction: column;
  padding: .35rem .55rem .55rem; background: #111418; border: 1px solid #333a4b; border-radius: 4px; }
.vtile .l { color: #8892a2; font-size: 15px; line-height: 1.25; text-align: left; padding-right: 1.3rem; }
.vtile .v { flex: 1; display: flex; align-items: center; justify-content: center; text-align: center;
  font-size: 1.55rem; font-weight: 600; color: #eef1f5; line-height: 1.2; font-variant-numeric: tabular-nums; }
/* the model details page: the value sits in the middle of the whole tile (the label stays at the top, the tile is a bit taller so a two-line label clears it) */
.vtiles.mid .vtile { min-height: 6.8rem; }
.vtiles.mid .vtile .v { position: absolute; inset: 0; pointer-events: none; }
.vtiles.mid .vtile .q { z-index: 2; }
.vnote { color: #b4bcc9; font-size: .85rem; line-height: 1.5; margin: .1rem 0 .35rem; }
table.vtable { border-collapse: collapse; width: 100%; font-size: .85rem; margin-top: .4rem; font-variant-numeric: tabular-nums; }
table.vtable th { color: #8892a2; font-weight: 600; font-size: .78rem; letter-spacing: .04em; background: #171a21; text-align: center; white-space: nowrap;
  padding: .35rem .55rem; border-bottom: 1px solid #333a4b; }
table.vtable th, table.vtable td { border-top: 0 !important; border-left: 0 !important; border-right: 0 !important; }
table.vtable td { padding: .35rem .55rem; border-bottom: 1px solid #333a4b; vertical-align: middle; }
table.vtable td.c { text-align: center; white-space: nowrap; }
table.vtable td.l { text-align: left; }
table.vtable td.nw { white-space: nowrap; }
table.vtable td ul { margin: 0; padding-left: 1.1rem; }
table.vtable td li { margin: 0; }
table.vtable tbody tr:hover td { background: #1f2430; }
.vtile .q { position: absolute; top: .3rem; right: .45rem; width: 1rem; height: 1rem; border: 1px solid #8892a2; border-radius: 50%;
  color: #8892a2; font-size: .68rem; line-height: .95rem; text-align: center; cursor: help; }
/* the model picker of the details page: a bigger label and dropdown */
div[class*="st-key-modelpick"] [data-testid="stWidgetLabel"] p { font-size: 1.15rem; font-weight: 700; }
div[class*="st-key-modelpick"] [data-testid="stSelectbox"] { font-size: 1.15rem; }
div[class*="st-key-modelpick"] .react-aria-ComboBox > div, div[class*="st-key-modelpick"] div[data-baseweb="select"] > div { min-height: 3.1rem; }
div[class*="st-key-modelpick"] [data-testid="stSelectbox"] input, div[class*="st-key-modelpick"] [data-testid="stSelectbox"] div { font-size: 1.15rem; }
/* quick filters (model list): one flat bar, a small label and round chips per group; a chosen chip is filled blue */
/* quick filters: ONE flat bar per list; each dimension is a label and a segmented control (All | value | value ...) with dividers between them
   (st.segmented_control, helper filter_bar) */
div[class*="st-key-filterbar"] { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; }
div[class*="st-key-filterbar"] [data-testid="stHorizontalBlock"] { gap: 16px !important; flex-wrap: wrap; align-items: center; }
div[class*="st-key-filterbar"] [data-testid="stColumn"] { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
div[class*="st-key-filterbar"] [data-testid="stColumn"] + [data-testid="stColumn"] { border-left: 1px solid #30363d; padding-left: 16px; }
div[class*="st-key-filterbar"] [data-testid="stButtonGroup"] { display: flex; flex-direction: row; align-items: center; gap: 8px; }
div[class*="st-key-filterbar"] [data-testid="stWidgetLabel"] { min-height: 0; margin: 0; }
div[class*="st-key-filterbar"] [data-testid="stWidgetLabel"] p { font-size: 12px; font-weight: 500; letter-spacing: 0; color: #8b949e; margin: 0; white-space: nowrap; }
div[class*="st-key-filterbar"] [role="radiogroup"] { display: inline-flex; gap: 0; background: #0d1117; padding: 2px; border-radius: 6px; border: 1px solid #21262d; }
div[class*="st-key-filterbar"] button[data-variant="segmented_control"] { background: transparent; color: #8b949e; border: 0; border-radius: 4px;
  padding: 4px 10px; min-height: 0; font-size: 12px; font-weight: 400; box-shadow: none; }
div[class*="st-key-filterbar"] button[data-variant="segmented_control"] p { font-size: 12px; }
div[class*="st-key-filterbar"] button[data-variant="segmented_control"]:hover { color: #f0f6fc; }
div[class*="st-key-filterbar"] button[data-variant="segmented_control"][aria-checked="true"], div[class*="st-key-filterbar"] button[data-variant="segmented_control"][aria-checked="true"]:hover,
div[class*="st-key-filterbar"] button[data-variant="segmented_control"][aria-checked="true"]:focus { background: #1f6feb !important; color: #fff !important; font-weight: 500; }
/* the action bar under a management list: safe actions on the left (rename, copy details in blue, a hint), the dangerous one on the right */
div[class*="st-key-actionbar"] { border-top: 1px solid #30363d; margin-top: 0; padding-top: 12px; }
div[class*="st-key-digest-off-"] button { background: #1f6feb !important; color: #fff !important; border-color: rgba(240,246,252,.1) !important; font-weight: 500 !important; }
div[class*="st-key-actionbar"] .act-note, div[class*="st-key-actionbar"] .act-err { font-size: 12px; }
div[class*="st-key-actionbar"] .act-note { color: #8b949e; }
table.vtable.doc th { text-align: left; } table.vtable.doc td { vertical-align: top; }
table.vtable.cmp { table-layout: fixed; }  /* compare: equal model columns, long data lists wrap */
table.vtable.cmp th:first-child { width: 12rem; } table.vtable.cmp th:last-child { width: 3.5rem; }
table.vtable.cmp td { overflow-wrap: anywhere; }
table.vtable td.best { color: #4aa8ff; font-weight: 700; background: rgba(74, 168, 255, .13); }
/* left navigation (Dashboard style): brand, section headings, one full-width entry per page, the active one highlighted */
section[data-testid="stSidebar"] { background: #171a21 !important; border-right: 1px solid #000; }
/* a narrower navigation (Streamlit's default is 300px); the brand keeps its own width on two lines, long entries are not wrapped. Only while
   it is open: a collapsed sidebar is moved away by Streamlit with its own width */
section[data-testid="stSidebar"]:not([aria-expanded="false"]) { width: 14rem !important; min-width: 14rem !important; max-width: 14rem !important; }
.nav-brand { white-space: nowrap; }
.nav-brand { display: flex; align-items: center; gap: .55rem; font-weight: 700; color: #fff; line-height: 1.25; font-size: .95rem;
  padding: .2rem 0 .7rem; border-bottom: 1px solid #333a4b; margin-bottom: .2rem; }
.nav-brand .nav-icon { font-size: 1.5rem; }
.navsec { font-size: .68rem; font-weight: 700; letter-spacing: .14em; color: #8892a2; padding: .6rem .2rem .15rem; line-height: 1.2; }
div[class*="st-key-nav-"] button { justify-content: flex-start !important; background: transparent !important;
  border: 0 !important; color: #b4bcc9 !important; font-weight: 500 !important; padding: .45rem .7rem !important; min-height: 0 !important; }
div[class*="st-key-nav-"] button:hover { color: #eef1f5 !important; background: #1f2430 !important; }
div[class*="st-key-navitem-"]:has(.nav-on) button { color: #fff !important; background: #1d3a5c !important; box-shadow: inset 3px 0 0 #4aa8ff; }
div[class*="st-key-navitem-"] .stElementContainer:has(.nav-on) { display: none; }
div[class*="st-key-nav-"] button > div { justify-content: flex-start !important; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .3rem; }
section[data-testid="stSidebar"] [data-testid="stMarkdown"], section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
/* the current job sits at the bottom of the navigation */
[data-testid="stSidebarUserContent"] { min-height: calc(100vh - 2.5rem); display: flex; flex-direction: column; padding-bottom: 1rem !important; }
[data-testid="stSidebarUserContent"] > div:first-child { flex: 1; display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] > div:first-child > [data-testid="stVerticalBlock"] { flex: 1; }
[data-testid="stLayoutWrapper"]:has(> .st-key-side-status), .st-key-side-status { margin-top: auto !important; }
.st-key-scrolltop, .st-key-scrolltop iframe { height: 0 !important; min-height: 0 !important; margin: 0 !important; overflow: hidden; }
.st-key-side-status { border-top: 1px solid #333a4b; padding-top: .2rem; }
/* job list: one framed row per job, the left edge coloured by state */
div[class*="st-key-qrow-"] { background: #111418; border: 1px solid #333a4b; border-radius: 6px; padding: .45rem .8rem; }
div[class*="st-key-qrow-running"], div[class*="st-key-qrow-queued"] { border-left: 4px solid #4aa8ff; }
div[class*="st-key-qrow-waiting"] { border-left: 4px solid #e0a410; }
div[class*="st-key-qrow-done"] { border-left: 4px solid #3fa83f; }
div[class*="st-key-qrow-failed"], div[class*="st-key-qrow-interrupted"] { border-left: 4px solid #ec6a6a; }
div[class*="st-key-qrow-cancelled"] { border-left: 4px solid #8892a2; }
div[class*="st-key-qrow-lost"] { border-left: 4px solid #e8672f; }
.side-state.lost { color: #e8672f; font-size: .8rem; }
.st-key-qhead { padding: 0 .8rem 0 calc(.8rem + 4px); color: #b4bcc9; }
.side-state.failed, .side-state.interrupted { color: #ec6a6a; } .side-state.done { color: #3fa83f; } .side-state.cancelled { color: #8892a2; }
</style>
"""
