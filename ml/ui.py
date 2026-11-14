"""ML UI: train value models and browse them (Streamlit).

    streamlit run ml/ui.py --server.address localhost      (or ml/start-ui.sh / ml\\start-ui.cmd)

Tabs: 訓練 (choose dumps and parameters, start a background job, live loss curve) and 模型清單 (every model in
ml/models with its .meta.json: parameters, data, validation, feature importance, match win rates; compare two).
Jobs run in their own process (jobs.py): closing this page or the UI does not stop them.
Reads the same folders as the Dashboard: results/ (PR_RESULTS_DIR overrides) and ml/models/.
"""
import datetime
import glob
import json
import os
import time

import altair as alt
import pandas as pd
import streamlit as st

import jobs
import modelmeta
import positions
import train_lgbm
import train_mlp

ROOT = jobs.ROOT
MODELS_DIR = os.path.join(ROOT, "ml", "models")
DASHBOARD_URL = "http://localhost:5080"

STATE_TEXT = {"queued": "排隊中", "running": "執行中", "done": "完成", "failed": "失敗", "cancelled": "已取消",
              "interrupted": "中斷（程序已不在）"}
KIND_TEXT = {"train_lgbm": "LightGBM", "train_mlp": "MLP", "lightgbm": "LightGBM", "mlp": "MLP"}


def rel(path):
    """Path relative to the project root with forward slashes (what configs and meta files store)."""
    try:
        r = os.path.relpath(os.path.abspath(path), ROOT)
    except ValueError:  # other drive on Windows
        return path.replace(os.sep, "/")
    return path.replace(os.sep, "/") if r.startswith("..") else r.replace(os.sep, "/")


def absolute(path):
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


# ---------------------------------------------------------------- data and models on disk

@st.cache_data(show_spinner=False)
def _dump_info(path, mtime):
    try:
        m = positions.read_meta(path)
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as e:
        return {"path": rel(path), "error": scrub(str(e))}
    strategies = [s.get("strategy") for s in m.get("seats", [])]
    models = sorted({os.path.basename(str((s.get("params") or {}).get("valueModel"))) for s in m.get("seats", [])
                     if (s.get("params") or {}).get("valueModel")})
    return {"path": rel(path), "來源": m.get("name") or os.path.basename(path), "人數": m["players"],
            "局數": m["games"], "列數": m["rows"], "狀態": m["status"], "抽樣率": m["rate"],
            "特徵版本": m["featureVersion"], "大小 MB": round(os.path.getsize(path) / 1e6, 1),
            "策略": "、".join(dict.fromkeys(strategies)), "自我對戰模型": "、".join(models)}


def scrub(message):
    """Never show the machine's full project path (same rule as the Dashboard)."""
    return message.replace(ROOT + os.sep, "").replace(ROOT, ".")


def list_dumps():
    """Readable dumps, plus 'writing' entries for dumps still being produced (no metadata yet, file growing)."""
    out = []
    for p in sorted(glob.glob(os.path.join(jobs.results_dir(), "ml", "*.bin"))):
        if not os.path.exists(p + ".json") and time.time() - os.path.getmtime(p) < 300:
            out.append({"path": rel(p), "writing": True, "大小 MB": round(os.path.getsize(p) / 1e6, 1)})
            continue
        out.append(_dump_info(p, os.path.getmtime(p + ".json") if os.path.exists(p + ".json") else 0))
    return out


def model_files():
    out = []
    for p in sorted(glob.glob(os.path.join(MODELS_DIR, "*"))):
        if p.endswith((".meta.json", ".check.txt")) or not p.endswith((".txt", ".json")):
            continue
        out.append(p)
    return out


@st.cache_data(show_spinner=False)
def _model_meta(path, mtime):
    try:
        return modelmeta.read(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def model_meta(path):
    mp = path + ".meta.json"
    return _model_meta(path, os.path.getmtime(mp) if os.path.exists(mp) else 0)


def describe_match(m):
    """Short label: '300 次 vs 原版 MCTS 300＋cheap-engine＋build-first'."""
    parts = []
    for o in m["others"]:
        if o["strategy"] == "mcts":
            parts.append(f"原版 MCTS {o.get('simulations') or ''}".strip() if not o.get("valueModel")
                         else f"MCTS＋{os.path.basename(o['valueModel'])}")
        else:
            parts.append(o["strategy"])
    leaf = f"，leafRollout {m['leafRollout']}" if m.get("leafRollout") else ""
    return f"{m.get('simulations')} 次{leaf} vs " + "＋".join(parts)


def best_vs_default(meta):
    """Highest win share in a match against the original MCTS (the headline number of section 10)."""
    rows = [m for m in meta.get("matches", []) if any(o["strategy"] == "mcts" and not o.get("valueModel") for o in m["others"])]
    return max(rows, key=lambda m: m["winShare"]) if rows else None


# ---------------------------------------------------------------- 訓練

PARAM_HELP = {
    "rounds": ("樹的數量", "400"),
    "leaves": ("每棵樹的葉子數", "63"),
    "lr": ("學習率", "0.05"),
    "min_leaf": ("每片葉子最少列數", "200"),
    "feature_fraction": ("每棵樹用的特徵比例", "0.8"),
    "bagging_fraction": ("每棵樹用的資料比例", "0.8"),
    "early_stopping": ("幾回合沒進步就停", "30"),
    "threads": ("執行緒數（0＝全部）", "0"),
    "hidden": ("隱藏層大小（逗號分隔；越大推論越慢）", "256,128"),
    "epochs": ("最多幾個 epoch", "12"),
    "batch": ("批次大小", "1024"),
    "l2": ("L2 正規化", "1e-5"),
    "patience": ("幾個 epoch 沒進步就停", "3"),
    "valid": ("驗證集比例（依局切）", "0.1"),
    "seed": ("亂數種子", "1"),
}


def param_inputs(defaults, key):
    """One input per parameter, typed after the default value."""
    values = {}
    cols = st.columns(3)
    for i, (name, default) in enumerate(defaults.items()):
        label, _ = PARAM_HELP.get(name, (name, ""))
        title = f"{label}（{name}）"
        tip = f"命令列參數 --{name.replace('_', '-')}，預設 {default}"
        with cols[i % 3]:
            k = f"{key}-{name}"
            if isinstance(default, int) and not isinstance(default, bool):
                values[name] = st.number_input(title, value=default, step=1, help=tip, key=k)
            elif isinstance(default, float):
                values[name] = st.number_input(title, value=default, format="%g", help=tip, key=k)
            else:
                values[name] = st.text_input(title, value=str(default), help=tip, key=k)
    return values


def training_tab():
    dumps = list_dumps()
    bad = [d for d in dumps if "error" in d]
    writing = [d for d in dumps if d.get("writing")]
    good = [d for d in dumps if "error" not in d and not d.get("writing")]
    st.subheader("1. 選訓練資料")
    if not good:
        for d in writing:
            st.info(f"`{d['path']}` 產生中（目前 {d['大小 MB']} MB）。")
        st.info("`results/ml/` 裡還沒有訓練資料。先用 Runner 產生（見 `ml/README.md`，第 2 階段會在這裡加「資料」頁）。")
        return
    players = sorted({d["人數"] for d in good})
    p = st.radio("人數（模型依人數分開）", players, index=len(players) - 1, horizontal=True, format_func=lambda n: f"{n} 人局")
    rows = [d for d in good if d["人數"] == p]
    df = pd.DataFrame(rows).drop(columns=["path"]).set_index(pd.Index([r["path"] for r in rows], name="檔案"))
    picked = st.dataframe(df, on_select="rerun", selection_mode="multi-row", use_container_width=True,
                          column_config={"列數": st.column_config.NumberColumn(format="localized"),
                                         "局數": st.column_config.NumberColumn(format="localized")})
    chosen = [rows[i] for i in picked.selection.rows]
    for d in writing:
        st.info(f"`{d['path']}` 產生中（目前 {d['大小 MB']} MB），完成後才會出現在表格裡。")
    for d in bad:
        st.warning(f"讀不了 `{d['path']}`：{d['error']}")
    versions = {d["特徵版本"] for d in chosen}
    if len(versions) > 1:
        st.error("選到的資料特徵版本不同，不能一起訓練。")
    total = sum(d["列數"] for d in chosen)
    if chosen:
        st.caption(f"已選 {len(chosen)} 份、{total:,} 列。LightGBM 約需 {total * 430 * 4 * 2.2 / 1e9:.1f} GB 記憶體，MLP 約 {total * 430 * 2 * 1.5 / 1e9:.1f} GB。")
    else:
        st.caption("在表格左側勾選要用的資料（可多選）。")

    st.subheader("2. 模型與參數")
    kind = st.radio("模型", ["train_lgbm", "train_mlp"], format_func=lambda k: KIND_TEXT[k], horizontal=True)
    defaults = dict(train_lgbm.DEFAULTS if kind == "train_lgbm" else train_mlp.DEFAULTS)
    options = param_inputs(defaults, kind)
    ext = ".txt" if kind == "train_lgbm" else ".json"
    stamp = datetime.datetime.now().strftime("%m%d-%H%M")
    name = st.text_input("模型名稱（存到 ml/models/，副檔名自動加）", value=f"{p}p-{'lgbm' if kind == 'train_lgbm' else 'mlp'}-{stamp}")
    name = name.strip()
    if name.endswith(ext):
        name = name[:-len(ext)]
    out = os.path.join(MODELS_DIR, name + ext)
    exists = os.path.exists(out)
    overwrite = st.checkbox(f"覆寫已存在的 `{name + ext}`", value=False) if exists else True

    active = jobs.active_job()
    problems = []
    if not chosen:
        problems.append("還沒選資料")
    if len(versions) > 1:
        problems.append("特徵版本不同")
    if not name or any(c in name for c in '/\\:*?"<>|'):
        problems.append("模型名稱不能空白或含路徑符號")
    if exists and not overwrite:
        problems.append("模型已存在")
    if active:
        problems.append(f"另一個工作執行中：{active['title']}")
    if st.button("開始訓練", type="primary", disabled=bool(problems)):
        spec = {"data": [d["path"] for d in chosen], "out": rel(out), "options": options}
        try:
            st.session_state["job-select"] = jobs.start(kind, f"{KIND_TEXT[kind]} → {name + ext}", spec)  # follow the new job
            st.rerun()
        except (RuntimeError, ValueError) as e:
            st.error(str(e))
    if problems:
        st.caption("無法開始：" + "；".join(problems))

    st.subheader("3. 工作")
    job_panel()


@st.fragment(run_every=2)
def job_panel():
    all_jobs = jobs.list_jobs()
    if not all_jobs:
        st.caption("還沒有工作。")
        return
    # the label carries no state: the dropdown does not refresh the text of an option that is already shown
    labels = {j["id"]: f"{j['title']}（{j.get('created', '').replace('T', ' ').rstrip('Z')} UTC）" for j in all_jobs}
    if st.session_state.get("job-select") not in labels:
        st.session_state.pop("job-select", None)
    job_id = st.selectbox("工作", list(labels), format_func=labels.get, key="job-select")
    job = jobs.read_job(job_id)
    state = job["state"]
    # this panel refreshes alone every 2 s; when any job changes state, rerun the whole page (start button, model list)
    signature = tuple((j["id"], j["state"]) for j in all_jobs)
    if st.session_state.get("job-signature") not in (None, signature):
        st.session_state["job-signature"] = signature
        st.rerun(scope="app")
    st.session_state["job-signature"] = signature
    evs = jobs.events(job_id)
    steps = [e for e in evs if e["stage"] in ("iteration", "epoch")]
    left, right = st.columns([2, 1])
    with left:
        if steps:
            last = steps[-1]
            n = last.get("iteration") or last.get("epoch")
            total = last.get("total") or n
            st.progress(min(1.0, n / max(1, total)), text=f"{STATE_TEXT.get(state, state)}：{n}/{total}"
                        f"{'（提早停止會更早結束）' if state == 'running' else ''}")
            curve = pd.DataFrame({"步": [e.get("iteration") or e.get("epoch") for e in steps],
                                  "驗證 loss（交叉熵）": [e["validLoss"] for e in steps]}).set_index("步")
            st.line_chart(curve, height=220)
        else:
            st.info(f"{STATE_TEXT.get(state, state)}：{'讀取資料中…' if state in ('queued', 'running') else ''}")
    with right:
        st.markdown(f"**狀態**：{STATE_TEXT.get(state, state)}")
        loaded = next((e for e in evs if e["stage"] == "loaded"), None)
        if loaded:
            st.markdown(f"**資料**：{loaded['rows']:,} 列（驗證 {loaded['validRows']:,}）")
        if job.get("started"):
            st.markdown(f"**開始**：{job['started']}")
        if job.get("finished"):
            st.markdown(f"**結束**：{job['finished']}")
        if state in ("queued", "running"):
            if st.button("取消這個工作", key=f"cancel-{job_id}"):
                jobs.cancel(job_id)
        if state == "failed":
            st.error(job.get("error", ""))
        if state == "interrupted":
            st.warning("程序已不在（電腦睡眠、關機或被終止），沒有產生模型。")
    if state == "done" and job.get("result"):
        v = job["result"]["validation"]
        c1, c2, c3 = st.columns(3)
        c1.metric("驗證交叉熵", f"{v['crossEntropy']:.4f}")
        c2.metric("驗證 MSE", f"{v['mse']:.4f}", help=f"常數基準 {v['constantMse']:.4f}")
        c3.metric("R²", f"{v['r2']:.3f}")
        st.success(f"模型已存到 `{job['result']['model']}`。到「模型清單」看細節；真正的判準是對戰勝率（第 2 階段會加「對戰驗證」頁）。")
    with st.expander("紀錄（最後 40 行）", expanded=state in ("failed",)):
        st.code(jobs.log_tail(job_id) or "（空的）", language=None)


# ---------------------------------------------------------------- 模型清單

def models_table(paths):
    rows = []
    for p in paths:
        meta = model_meta(p)
        name = os.path.basename(p)
        if not meta:
            rows.append({"模型": name, "種類": "LightGBM" if p.endswith(".txt") else "MLP", "備註": "沒有 .meta.json"})
            continue
        best = best_vs_default(meta)
        v = meta.get("validation") or {}
        rows.append({
            "模型": name, "種類": KIND_TEXT.get(meta["kind"], meta["kind"]), "人數": meta["players"],
            "建立": (meta.get("created") or "（補寫）")[:16].replace("T", " "),
            "資料列數": sum(d["rows"] for d in meta["data"]),
            "自我對戰資料": "、".join(sorted({os.path.basename(m) for d in meta["data"] for m in d.get("valueModels", [])})),
            "R²": v.get("r2"), "交叉熵": v.get("crossEntropy"),
            "對戰場數": len(meta.get("matches", [])),
            "對原版 MCTS 最佳勝率": best["winShare"] if best else None,
            "備註": "參數為補寫" if "note" in meta.get("params", {}) else "",
        })
    df = pd.DataFrame(rows)
    # text columns so that missing values read "—" instead of Streamlit's grey "None"
    fmt = {"R²": "{:.3f}", "交叉熵": "{:.4f}", "對原版 MCTS 最佳勝率": "{:.1%}", "資料列數": "{:,.0f}", "人數": "{:.0f}", "對戰場數": "{:.0f}"}
    for col, f in fmt.items():
        if col in df:
            df[col] = [f.format(v) if v is not None and v == v else "—" for v in df[col]]
    return df.fillna("")


def matches_frame(meta):
    rows = []
    for m in meta.get("matches", []):
        rows.append({"設定": m.get("config"), "對手": describe_match(m), "局數": m["games"], "種子": m["seed"],
                     "勝率": m["winShare"], "±95%": m.get("winShareCi95"), "平均分": m["avgScore"],
                     "對手勝率": "、".join(f"{o['strategy'] if not o.get('valueModel') else 'MCTS＋模型'} {o['winShare']:.1%}" for o in m["others"]),
                     "結果檔": m["result"]})
    return pd.DataFrame(rows)


def flat_params(meta):
    return {k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in (meta.get("params") or {}).items()}


def model_detail(path):
    meta = model_meta(path)
    name = os.path.basename(path)
    if not meta:
        st.warning(f"`{name}` 沒有 `.meta.json`（不知道怎麼訓練的）。")
        return
    v = meta.get("validation") or {}
    c = st.columns(4)
    c[0].metric("種類", KIND_TEXT.get(meta["kind"], meta["kind"]))
    c[1].metric("資料列數", f"{sum(d['rows'] for d in meta['data']):,}")
    c[2].metric("R²", f"{v['r2']:.3f}" if v.get("r2") is not None else "—")
    best = best_vs_default(meta)
    c[3].metric("對原版 MCTS 最佳勝率", f"{best['winShare']:.1%}" if best else "—", help=describe_match(best) if best else "還沒有對戰")

    st.markdown("**對戰結果**（判斷模型好壞的依據）")
    mf = matches_frame(meta)
    if mf.empty:
        st.caption("還沒有對戰紀錄。")
    else:
        st.dataframe(mf, hide_index=True, use_container_width=True,
                     column_config={"勝率": st.column_config.NumberColumn(format="percent"),
                                    "±95%": st.column_config.NumberColumn(format="percent"),
                                    "平均分": st.column_config.NumberColumn(format="%.1f")})
        st.caption(f"結果檔可以在 Dashboard（{DASHBOARD_URL}）的「結果」「比較」頁打開。")

    left, right = st.columns(2)
    with left:
        st.markdown("**訓練參數**")
        st.dataframe(pd.DataFrame(list(flat_params(meta).items()), columns=["參數", "值"]).astype(str),
                     hide_index=True, use_container_width=True)
    with right:
        st.markdown("**驗證（各回合段）**")
        if v.get("byRound"):
            st.dataframe(pd.DataFrame(v["byRound"]).rename(columns={"rounds": "回合", "rows": "列數", "mse": "MSE"}),
                         hide_index=True, use_container_width=True)
        else:
            st.caption("沒有紀錄。")
        st.caption("驗證成績只是檢查訓練有沒有壞掉；資料分布不同時 R² 不能互相比較。")

    st.markdown("**訓練資料**")
    st.dataframe(pd.DataFrame([{"來源": d["source"], "局數": d["games"], "列數": d["rows"], "抽樣率": d["rate"],
                                "狀態": d["status"], "策略": "、".join(dict.fromkeys(s for s in d["strategies"] if s)),
                                "自我對戰模型": "、".join(os.path.basename(m) for m in d.get("valueModels", [])),
                                "檔案": d["path"]} for d in meta["data"]]),
                 hide_index=True, use_container_width=True)

    curve = (meta.get("training") or {}).get("validLossCurve")
    feats = meta.get("topFeatures") or []
    left, right = st.columns(2)
    with left:
        st.markdown("**驗證 loss 曲線**")
        if curve:
            st.line_chart(pd.DataFrame({"驗證 loss": curve}, index=pd.RangeIndex(1, len(curve) + 1, name="步")), height=240)
        else:
            st.caption("沒有紀錄（舊模型或補寫的 meta）。")
    with right:
        st.markdown("**特徵重要度（前 20，gain）**")
        if feats:
            fd = pd.DataFrame(feats[:20])
            chart = alt.Chart(fd).mark_bar().encode(x=alt.X("gain:Q", title="gain"),
                                                    y=alt.Y("name:N", sort="-x", title=None),
                                                    tooltip=["name", alt.Tooltip("gain:Q", format=",.0f")])
            st.altair_chart(chart.properties(height=420), use_container_width=True)
        else:
            st.caption("只有 LightGBM 有（MLP 或補寫的 meta 沒有）。")
    env = meta.get("environment") or {}
    env_text = "環境未記錄" if "note" in env else "・".join(f"{k} {val}" for k, val in env.items())
    st.caption(f"特徵版本 {meta['featureVersion']}（{meta['featureCount']} 個）・建立 {meta.get('created') or '（補寫）'}・{env_text}")


def compare(paths):
    metas = {os.path.basename(p): model_meta(p) for p in paths}
    names = list(metas)
    keys = []
    for m in metas.values():
        for k in flat_params(m or {}):
            if k not in keys:
                keys.append(k)
    rows = []
    for k in keys:
        vals = [str(flat_params(metas[n] or {}).get(k, "—")) for n in names]
        rows.append({"參數": k, **dict(zip(names, vals)), "不同": "●" if len(set(vals)) > 1 else ""})
    for label, f in [("資料列數", lambda m: f"{sum(d['rows'] for d in m['data']):,}"),
                     ("資料來源", lambda m: "、".join(d["source"] for d in m["data"])),
                     ("R²", lambda m: f"{(m.get('validation') or {}).get('r2') or 0:.3f}"),
                     ("對原版 MCTS 最佳勝率", lambda m: f"{best_vs_default(m)['winShare']:.1%}" if best_vs_default(m) else "—")]:
        vals = [f(metas[n]) if metas[n] else "—" for n in names]
        rows.insert(0, {"參數": label, **dict(zip(names, vals)), "不同": "●" if len(set(vals)) > 1 else ""})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def models_tab():
    paths = model_files()
    if not paths:
        st.info("`ml/models/` 裡還沒有模型。")
        return
    table = models_table(paths)
    st.dataframe(table, hide_index=True, use_container_width=True)
    by_name = {os.path.basename(p): p for p in paths}
    mode = st.radio("檢視", ["單一模型", "並排比較"], horizontal=True)
    if mode == "單一模型":
        # open on the strongest model (best win share against the original MCTS)
        scores = [(best_vs_default(model_meta(p))["winShare"] if model_meta(p) and best_vs_default(model_meta(p)) else -1) for p in paths]
        name = st.selectbox("模型", list(by_name), index=scores.index(max(scores)))
        model_detail(by_name[name])
    else:
        names = st.multiselect("選兩個以上的模型", list(by_name), max_selections=4)
        if len(names) >= 2:
            compare([by_name[n] for n in names])
        else:
            st.caption("選兩個以上的模型來比較參數、資料與勝率。")


def main():
    st.set_page_config(page_title="波多黎各 ML", page_icon="🌱", layout="wide")
    st.title("波多黎各 ML：局面價值模型")
    st.caption(f"訓練在背景程序執行，關掉這個頁面或 UI 都不會中斷。模擬、結果與回放請用 Dashboard（{DASHBOARD_URL}）。")
    t1, t2 = st.tabs(["訓練", "模型清單"])
    with t1:
        training_tab()
    with t2:
        models_tab()


main()
