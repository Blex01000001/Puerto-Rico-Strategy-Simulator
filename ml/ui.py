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
import re
import time

import streamlit as st

import check_env

if check_env.missing_modules():
    # started with a Python that lacks the packages (e.g. pip installed them into another Python): say so plainly
    st.set_page_config(page_title="Puerto Rico Machine Learning", page_icon="🌱")
    st.error(f"這個 Python 缺少 ML UI 需要的套件：{', '.join(check_env.missing_modules())}")
    st.markdown(f"ML UI 現在用的 Python：`{check_env.sys.executable}`")
    st.markdown("在終端機執行下面這一行（指定同一個 Python，套件才會裝到對的地方），然後關掉 ML UI 再啟動一次：")
    st.code(check_env.fix_command(), language=None)
    st.caption("電腦上有好幾個 Python（例如 Anaconda 和 python.org）時，直接打 `pip install` 可能裝到另一個 Python。")
    st.stop()

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402

import fingerprint  # noqa: E402
import jobs  # noqa: E402
import modelmeta  # noqa: E402
import positions  # noqa: E402
import train_lgbm  # noqa: E402
import train_mlp  # noqa: E402

ROOT = jobs.ROOT
MODELS_DIR = os.path.join(ROOT, "ml", "models")                    # official models (tracked by git)
LOCAL_DIR = os.path.join(ROOT, "ml", "local")                      # this machine's workspace (ignored by git)
LOCAL_MODELS = os.path.join(LOCAL_DIR, "models")
LOCAL_CONFIGS = os.path.join(LOCAL_DIR, "data-configs")
LOCAL_MATCHES = os.path.join(LOCAL_DIR, "matches")
DASHBOARD_URL = "http://localhost:5080"

STATE_TEXT = {"waiting": "排隊中", "queued": "啟動中", "running": "執行中", "done": "完成", "failed": "失敗", "cancelled": "已取消",
              "interrupted": "中斷（程序已不在）", "lost": "失聯（程序還在，但沒有回報）"}
LOST_TEXT = ("失聯：程序還在執行，但超過 30 秒沒有回報進度。排隊的工作會先暫停，等它結束或回報恢復；"
             "確定它卡住了再按「強制結束」（會直接結束它與它啟動的 Runner）。")
KIND_TEXT = {"train_lgbm": "LightGBM", "train_mlp": "MLP", "lightgbm": "LightGBM", "mlp": "MLP", "dump": "產生資料", "match": "對戰驗證"}


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
    meta = {k: v for k, v in m.items() if k != "featureNames"}
    strategies = [s.get("strategy") for s in m.get("seats", [])]
    models = sorted({os.path.basename(str((s.get("params") or {}).get("valueModel"))) for s in m.get("seats", [])
                     if (s.get("params") or {}).get("valueModel")})
    return {"path": rel(path), "來源": m.get("name") or os.path.basename(path), "人數": m["players"],
            "局數": m["games"], "列數": m["rows"], "狀態": m["status"], "抽樣率": m["rate"],
            "特徵版本": m["featureVersion"], "大小 MB": round(os.path.getsize(path) / 1e6, 1),
            "策略": "、".join(dict.fromkeys(strategies)), "自我對戰模型": "、".join(models), "_meta": meta}


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
        info = dict(_dump_info(p, os.path.getmtime(p + ".json") if os.path.exists(p + ".json") else 0))
        if "_meta" in info:
            # outside the cache: a value model a self-play dump used may have been replaced since
            info["_recipe"] = fingerprint.dump_recipe(info["_meta"])
            info["_fp"] = fingerprint.fingerprint(info["_recipe"])
            info["_rules"] = (info["_recipe"]["ruleset"], info["_recipe"]["rulesRevision"])
            info["_stale"] = fingerprint.stale_notes(info["_recipe"])
            info["hash"] = fingerprint.short(info["_fp"])
            info["規則版本"] = fingerprint.rules_name(info["_recipe"]["rulesRevision"], info["_recipe"]["ruleset"])
            info["版本狀態"] = version_text(info["_stale"])
            info["引擎 commit"] = info["_meta"].get("engineCommit", "—")
        out.append(info)
    return out


def version_text(notes):
    """'最新', or what is older than this checkout's engine ('舊：規則 base-v1 → base-v2；harbor-rush-v1 → v2')."""
    return "最新" if not notes else "舊：" + "；".join(notes)


def entry_stale(rules_revision, ruleset, revisions, strategies=()):
    """stale_notes for a recorded data / match entry (model metadata keeps no full recipe). Entries from before strategy
    revisions were recorded count as revision 1 of the strategies they name."""
    if not revisions:
        revisions = {str(n).lower(): 1 for n in strategies if n}
    return fingerprint.stale_notes({"rulesRevision": rules_revision or 1, "ruleset": ruleset, "seats": [{"revisions": revisions}]})


def model_stale(meta):
    """Everything about a model's data that is older than this checkout's engine."""
    notes = []
    for d in meta.get("data", []):
        for n in entry_stale(d.get("rulesRevision", 1), d.get("ruleset"), d.get("revisions"), d.get("strategies", [])):
            if n not in notes:
                notes.append(n)
    return notes


def table_view(rows, path_as=None):
    """Dump rows for display: no internal columns (those starting with _); the path column is dropped or renamed."""
    df = pd.DataFrame(rows)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    return df.rename(columns={"path": path_as}) if path_as else df.drop(columns=["path"])


def models_using(dump_rel):
    """Names of the models that were trained on this dump file (by the path recorded in their metadata)."""
    out = []
    for mp in model_files():
        meta = model_meta(mp)
        if meta and any(str(d.get("path", "")).replace("\\", "/") == dump_rel for d in meta.get("data", [])):
            out.append(os.path.basename(mp))
    return out


def job_reads(job):
    """Files a waiting / starting / running job will read (repo-relative, forward slashes): training data, the model a match
    plays, and the value models named in its config."""
    spec = job.get("spec", {})
    paths = list(spec.get("data") or [])
    if spec.get("model"):
        paths.append(spec["model"])
    if spec.get("config"):
        cfg = read_config(absolute(spec["config"]))
        for seat in (cfg or {}).get("seats", []):
            vm = (seat.get("params") or {}).get("valueModel")
            if vm:
                paths.append(vm)
    return {str(x).replace("\\", "/") for x in paths}


def pending_readers(out_rel):
    """Titles of the waiting / starting / running jobs that will read this file (overwriting it would change their input)."""
    want = out_rel.replace("\\", "/")
    return [j["title"] for j in jobs.list_jobs() if j["state"] in ("waiting",) + jobs.BUSY and want in job_reads(j)]


def reader_problem(out_rel):
    titles = pending_readers(out_rel)
    return f"排隊中或執行中的工作「{titles[0]}」要讀這個檔案，不能覆寫，換一個名稱" if titles else None


def same_name_notice(noun, exists, old, new, users=(), names=None):
    """Under a name field: what is already there under this name, and is it the same recipe?"""
    if not exists:
        return
    if old is None:
        st.warning(f"同名{noun}已存在，但讀不出它的參數，無法比較。")
    elif fingerprint.fingerprint(old) == fingerprint.fingerprint(new):
        st.info(f"同名{noun}的參數**完全相同**（hash {fingerprint.short(fingerprint.fingerprint(new))}）：重跑只會得到同一份結果，不需要覆寫。")
    else:
        st.warning(f"同名{noun}的參數**不同**，覆寫會換掉它：\n\n" + "\n".join(f"- {d}" for d in fingerprint.describe(old, new, names)))
    if users:
        st.warning("用過它的模型：" + "、".join(f"`{u}`" for u in users) + "。覆寫後這些模型的紀錄會對不上資料，建議換一個名稱。")


def model_files():
    """Official models (ml/models) first, then local ones (ml/local/models)."""
    out = []
    for folder in (MODELS_DIR, LOCAL_MODELS):
        for p in sorted(glob.glob(os.path.join(folder, "*"))):
            if p.endswith((".meta.json", ".check.txt")) or not p.endswith((".txt", ".json")):
                continue
            out.append(p)
    return out


def place_of(path):
    return "正式" if os.path.dirname(os.path.abspath(path)) == os.path.abspath(MODELS_DIR) else "本機"


def model_path(name):
    """Full path of a model by file name (names are unique across ml/models and ml/local/models)."""
    return next((p for p in model_files() if os.path.basename(p) == name), os.path.join(MODELS_DIR, name))


def model_name_taken(name):
    return any(os.path.exists(os.path.join(d, name)) for d in (MODELS_DIR, LOCAL_MODELS))


@st.cache_data(show_spinner=False)
def _model_meta(path, mtime):
    try:
        return modelmeta.read(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def model_meta(path):
    mp = path + ".meta.json"
    rec = os.path.join(LOCAL_DIR, "match-records", os.path.basename(path) + ".matches.json")
    stamp = (os.path.getmtime(mp) if os.path.exists(mp) else 0, os.path.getmtime(rec) if os.path.exists(rec) else 0)
    return _model_meta(path, stamp)


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
    "backend": ("訓練引擎（auto＝有 PyTorch 就用）", "auto"),
    "device": ("PyTorch 裝置（auto／cpu／cuda）", "auto"),
    "valid": ("驗證集比例（依局切）", "0.1"),
    "seed": ("亂數種子", "1"),
}


# (參數, 預設, 作用, 調高, 調低, 建議)
PARAM_DOC = {
    "train_lgbm": [
        ("rounds 樹的數量", "400", "最多建幾棵樹（每棵修正前面的誤差）", "更細、訓練更久、推論變慢；有提早停止，不會無限變好", "學不完整、估值粗糙", "資料 300 萬列以內 400 夠用；資料更多可到 600～800"),
        ("leaves 每棵樹的葉子數", "63", "每棵樹能切出幾種情況，決定模型複雜度", "能學更細的規律，但容易記住雜訊（過擬合）、推論變慢", "太簡單，學不到組合效果", "31～127；先別動"),
        ("lr 學習率", "0.05", "每棵樹修正的幅度", "收斂快但較粗糙、容易過擬合", "更細但要更多樹（rounds 要跟著加）", "0.03～0.1；調小就加 rounds"),
        ("min_leaf 每片葉子最少列數", "200", "一個情況至少要有多少筆資料才能單獨成一片葉子", "更保守、更平滑", "會為少數局面硬切規則（雜訊）", "100～500；資料少時調高"),
        ("feature_fraction 特徵比例", "0.8", "每棵樹隨機只看這個比例的特徵", "每棵樹看得更全，但樹之間更像、較易過擬合", "多樣性高，但每棵樹資訊少", "0.6～0.9"),
        ("bagging_fraction 資料比例", "0.8", "每棵樹隨機只用這個比例的資料", "同上（資料面）", "訓練較快、更隨機", "0.6～0.9"),
        ("early_stopping 幾回合沒進步就停", "30", "驗證 loss 連續這麼多棵樹沒進步就停", "更有耐心，可能多長幾棵沒用的樹", "可能太早停", "20～50"),
        ("threads 執行緒數", "0", "用幾個 CPU 核心（0＝全部）", "—", "訓練較慢但電腦較不卡", "0；要同時做別的事時設成核心數一半"),
    ],
    "train_mlp": [
        ("hidden 隱藏層大小", "256,128", "神經網路每層的神經元數（逗號分隔，層數＝個數）", "能表達更複雜的估值，但推論變慢：MCTS 每個葉節點都要算一次，同時間內搜尋變少", "表達力不足", "128,64～256,128；不建議再加大"),
        ("epochs 最多幾個 epoch", "12", "整份資料最多看幾遍", "訓練更久（提早停止會擋下過擬合）", "可能還沒學完", "8～20；通常第 2～4 個 epoch 就最好"),
        ("batch 批次大小", "1024", "每次更新用幾筆資料", "每次更新較穩、GPU 上較快，但可能收斂較差", "雜訊大、CPU 上較慢", "512～4096（GPU 用大的）"),
        ("lr 學習率", "0.001", "Adam 每步的更新幅度（每 4 個 epoch 自動減半）", "收斂快但可能震盪或發散", "收斂很慢", "0.0005～0.003"),
        ("l2 L2 正規化", "1e-5", "懲罰太大的權重，防止過擬合", "更平滑、可能學不夠", "較易過擬合", "1e-6～1e-4"),
        ("patience 幾個 epoch 沒進步就停", "3", "驗證 loss 連續幾個 epoch 沒進步就停並保留最好的一輪", "更有耐心", "可能太早停", "2～5"),
        ("backend 訓練引擎", "auto", "auto＝有 PyTorch 就用，沒有就用 NumPy", "—", "—", "auto；兩者輸出同一種模型檔"),
        ("device 裝置", "auto", "PyTorch 用 CPU 或 GPU（auto＝有 GPU 就用）", "—", "—", "auto；只有 PyTorch 才有作用"),
    ],
    "common": [
        ("valid 驗證集比例", "0.1", "依「局」切出這個比例當驗證集（同一局不會同時在訓練與驗證）", "驗證更準，但訓練資料變少", "驗證數字較不可靠", "0.1"),
        ("seed 亂數種子", "1", "切驗證集、抽樣、初始化的亂數", "—", "—", "換種子可以確認結果不是運氣；LightGBM 同種子同資料會得到一樣的模型"),
    ],
}


def param_inputs(defaults, key):
    """One input per parameter, typed after the default value. The grid gives every label the same height
    (CSS .st-key-params), so a title that wraps in a narrow window does not shift its row."""
    values = {}
    with st.container(key="params"):
        cols = st.columns(3)
        for i, (name, default) in enumerate(defaults.items()):
            label, _ = PARAM_HELP.get(name, (name, ""))
            title = f"{label}（{name}）"
            tip = f"命令列參數 --{name.replace('_', '-')}，預設 {default}；詳細說明見頁面最下方的參數表"
            with cols[i % 3]:
                k = f"{key}-{name}"
                if isinstance(default, int) and not isinstance(default, bool):
                    values[name] = st.number_input(title, value=default, step=1, help=tip, key=k)
                elif isinstance(default, float):
                    values[name] = st.number_input(title, value=default, format="%g", help=tip, key=k)
                else:
                    values[name] = st.text_input(title, value=str(default), help=tip, key=k)
    return values


def grid(data, **kwargs):
    """st.dataframe with room for a horizontal scrollbar: Streamlit sizes a table to its rows exactly, so on Windows (a
    17 px scrollbar that takes space) the scrollbar of a wide table covered the last row. At most 10 rows are shown
    before the table scrolls vertically."""
    rows = len(getattr(data, "data", data))  # a pandas Styler keeps the frame in .data
    kwargs.setdefault("height", 35 * (min(rows, 10) + 1) + 2 + 18)
    return st.dataframe(data, **kwargs)


def busy_files(field):
    """Files that a waiting / starting / running job will read (they must not be deleted)."""
    used = set()
    for j in jobs.list_jobs():
        if j["state"] in ("waiting",) + jobs.BUSY:
            v = j.get("spec", {}).get(field)
            for f in (v if isinstance(v, list) else [v] if v else []):
                used.add(str(f).replace("\\", "/"))
    return used


def delete_gen():
    """Bumped after every deletion: tables with checkboxes put it in their key, so the old selection (row numbers that
    now point at other files) is dropped."""
    return st.session_state.get("del-gen", 0)


def delete_button(key, label, paths, extra_suffixes=(), busy=()):
    """A red delete button (right-aligned via the 'del-' key prefix) that asks for confirmation in a dialog; files a
    queued or running job needs are refused. A dialog closes with the rerun after deleting (a popover stayed open)."""
    with st.container(key=key):
        if st.button(label, key=f"{key}-open", disabled=not paths):
            confirm_delete(key, list(paths), tuple(extra_suffixes), tuple(busy))


@st.dialog("刪除檔案")
def confirm_delete(key, paths, extra_suffixes, busy):
    blocked = [p for p in paths if rel(p) in busy]
    if blocked:
        st.markdown('<span class="act-err">排隊中或執行中的工作會用到：' + "、".join(plain(rel(p)) for p in blocked) + "，不能刪除</span>",
                    unsafe_allow_html=True)
        if st.button("關閉", key=f"keep-{key}-close"):
            st.rerun()
        return
    st.markdown("確定刪除這些檔案？刪除後無法復原。")
    for p in paths:
        st.markdown(f"- `{rel(p)}`")
    c1, c2 = st.columns(2)
    if c1.button("取消", key=f"keep-{key}-cancel", width="stretch"):
        st.rerun()
    if c2.button("確定刪除", key=f"{key}-confirm", width="stretch"):
        for p in paths:
            for f in [p] + [p + suf for suf in extra_suffixes]:
                if os.path.exists(f):
                    os.remove(f)
        st.session_state["del-gen"] = delete_gen() + 1
        st.cache_data.clear()
        st.rerun()


def training_tab():
    dumps = list_dumps()
    bad = [d for d in dumps if "error" in d]
    writing = [d for d in dumps if d.get("writing")]
    good = [d for d in dumps if "error" not in d and not d.get("writing")]
    with card("train-data", "1. 選訓練資料"):
        if not good:
            for d in writing:
                st.info(f"`{d['path']}` 產生中（目前 {d['大小 MB']} MB）。")
            st.info(f"`results/ml/` 裡還沒有訓練資料。先到「{TAB_DATA}」頁產生。")
            return
        players = sorted({d["人數"] for d in good})
        p = st.radio("人數（模型依人數分開）", players, index=len(players) - 1, horizontal=True, format_func=lambda n: f"{n} 人局")
        rows = [d for d in good if d["人數"] == p]
        df = table_view(rows).set_index(pd.Index([r["path"] for r in rows], name="檔案"))
        picked = grid(df, on_select="rerun", selection_mode="multi-row", width="stretch", key=f"dumps-{delete_gen()}",
                              column_config={"列數": st.column_config.NumberColumn(format="localized"),
                                             "局數": st.column_config.NumberColumn(format="localized")})
        chosen = [rows[i] for i in picked.selection.rows]
        for d in writing:
            st.info(f"`{d['path']}` 產生中（目前 {d['大小 MB']} MB），完成後才會出現在表格裡。")
        for d in bad:
            st.warning(f"讀不了 `{d['path']}`：{d['error']}")
        versions = {d["特徵版本"] for d in chosen}
        total = sum(d["列數"] for d in chosen)
        c1, c2 = st.columns([4, 2.2], vertical_alignment="center")
        if chosen:
            c1.caption(f"已選 {len(chosen)} 份、{total:,} 列。LightGBM 約需 {total * 430 * 4 * 2.2 / 1e9:.1f} GB 記憶體，MLP 約 {total * 430 * 2 * 1.5 / 1e9:.1f} GB。")
        else:
            c1.caption("在表格左側勾選要用的資料（可多選）；勾選後也可以刪除。")
        with c2:
            delete_button("del-dumps", f"🗑 刪除勾選（{len(chosen)}）", [absolute(d["path"]) for d in chosen],
                          extra_suffixes=(".json",), busy=busy_files("data"))

    with card("train-model", "2. 模型與參數"):
        kind = st.radio("模型", ["train_lgbm", "train_mlp"], format_func=lambda k: KIND_TEXT[k], horizontal=True)
        defaults = dict(train_lgbm.DEFAULTS if kind == "train_lgbm" else train_mlp.DEFAULTS)
        options = param_inputs(defaults, kind)
        ext = ".txt" if kind == "train_lgbm" else ".json"
        stamp = datetime.datetime.now().strftime("%m%d-%H%M")
        name = st.text_input("模型名稱（存到本機工作區 ml/local/models/，副檔名自動加；之後可在「模型清單」設為正式模型）",
                             value=f"{p}p-{'lgbm' if kind == 'train_lgbm' else 'mlp'}-{stamp}")
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
            backend, device = train_mlp.resolve_backend(opts)
            opts = {**opts, "backend": backend, "device": device}
        new_recipe = fingerprint.model_recipe(kind_name, chosen[0]["特徵版本"], [d["_fp"] for d in chosen], opts) if chosen else None
        if chosen:
            by_fp = {}
            for d in chosen:
                by_fp.setdefault(d["_fp"], []).append(d["來源"])
            for names_ in by_fp.values():
                if len(names_) > 1:
                    st.warning("勾選的 " + "、".join(f"`{n}`" for n in names_) + " 參數完全相同（同一份資料），重複放進去只會讓模型多看一次同樣的局面。")
            rules = {d["_rules"] for d in chosen}
            if len(rules) > 1:
                st.warning(f"勾選的資料規則版本不一致（{'、'.join(fingerprint.rules_name(r, rs) for rs, r in sorted(rules))}），不建議一起訓練。")
            stale = [(d["來源"], d["_stale"]) for d in chosen if d["_stale"]]
            if stale:
                st.warning("勾選的資料有些是用舊版規則或舊版策略產生的，同樣的設定現在會得到不同的資料，建議重新產生：\n\n"
                           + "\n".join(f"- `{n}`：{'；'.join(notes)}" for n, notes in stale))
            fp_names = {d["_fp"]: d["來源"] for d in chosen}
            old_meta = model_meta(out) if exists else None
            old_recipe = (old_meta or {}).get("recipe")
            same_name_notice("模型", exists, old_recipe, new_recipe, names=fp_names)
            twins = [os.path.basename(mp) for mp in model_files() if (model_meta(mp) or {}).get("fingerprint") == fingerprint.fingerprint(new_recipe)
                     and mp != out]
            if twins:
                st.info("已經有相同配方（同樣的資料與參數）的模型：" + "、".join(f"`{t}`" for t in twins) + "。")
        overwrite = st.checkbox(f"覆寫已存在的 `{name + ext}`", value=False) if exists else True

        problems = []
        if not chosen:
            problems.append("還沒選資料")
        if len(versions) > 1:
            problems.append("選到的資料特徵版本不同，不能一起訓練")
        if not name or any(c in name for c in '/\\:*?"<>|'):
            problems.append("模型名稱不能空白或含路徑符號")
        if exists and not overwrite:
            problems.append("模型已存在（要覆寫請勾選）")
        if official_taken:
            problems.append(f"正式模型裡已經有 {name + ext}，換一個名稱")
        if pending_output(rel(out)):
            problems.append(f"排隊中或執行中的工作已經會寫 {name + ext}，換一個名稱")
        if exists and reader_problem(rel(out)):
            problems.append(reader_problem(rel(out)))
        if action_row("開始訓練", "start-train", problems):
            spec = {"data": [d["path"] for d in chosen], "out": rel(out), "options": options}
            start_job(kind, f"{KIND_TEXT[kind]} → {name + ext}", spec)

    with card("train-doc", "參數說明"):
        st.caption("每個參數的作用、預設值，以及調高、調低會怎樣。不確定就用預設值；判斷好壞只看「對戰驗證」的勝率。")
        doc = PARAM_DOC[kind] + PARAM_DOC["common"]
        st.table(pd.DataFrame(doc, columns=["參數", "預設", "作用", "調高會…", "調低會…", "建議"]).set_index("參數"))


# ---------------------------------------------------------------- jobs (shared by every tab)

TITLE = "Puerto Rico Machine Learning"
TAB_DATA, TAB_TRAIN, TAB_MATCH, TAB_MODELS, TAB_QUEUE = "模擬對局採樣", "模型訓練/蒸餾", "對戰驗證", "模型清單", "排程佇列"

# Same palette as the Dashboard (Dashboard/wwwroot/app.css); the base theme is in .streamlit/config.toml.
CSS = """
<style>
.block-container { padding-top: 2.9rem !important; padding-bottom: 2rem !important; }
[data-testid="stHeader"] { height: 2.5rem !important; background: transparent !important; }
h1 { padding-top: 0 !important; margin-bottom: .1rem !important; font-size: 1.7rem !important; }
[data-testid="stSidebarHeader"] { height: 1.6rem !important; padding-top: .3rem !important; padding-bottom: 0 !important; min-height: 0 !important; }
[data-testid="stSidebarUserContent"] { padding-top: .3rem !important; }
/* cards: st.container(border=True, key="card-...") */
div[class*="st-key-card-"] { background: #1f2430; border: 1px solid #333a4b !important; border-radius: 6px; padding: .55rem 1rem .8rem 1rem; }
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
/* metrics (模型清單: 種類, 資料列數, R², 最佳勝率) as framed tiles */
[data-testid="stMetric"] { background: #111418; border: 1px solid #333a4b; border-radius: 4px; padding: .45rem .8rem; }
[data-testid="stMetricValue"] > div { font-size: 1.7rem !important; }
/* delete buttons: red, at the right edge (delete_button wraps them in st.container(key="del-…")) */
div[class*="st-key-del-"] { align-items: flex-end !important; }
div[class*="st-key-del-"] [data-testid="stPopover"] { width: auto !important; }
div[class*="st-key-del-"] button { background: #c43c3c !important; border: 0 !important; color: #fff !important; font-weight: 600 !important; }
div[class*="st-key-del-"] button:hover:not(:disabled) { filter: brightness(1.12); }
div[class*="st-key-stop-"] button { background: #c43c3c !important; border: 0 !important; color: #fff !important; font-weight: 600 !important; }
div[class*="st-key-stop-"] button:hover:not(:disabled) { filter: brightness(1.12); }
div[class*="st-key-del-"] button:disabled { background: #4a2a2e !important; color: #b9a3a6 !important; }
/* buttons like the Dashboard: blue when they can start, locked otherwise */
button[kind="primary"] { background: #4aa8ff !important; border: 0 !important; color: #07131f !important; font-weight: 600 !important; }
button[kind="primary"]:hover:not(:disabled) { filter: brightness(1.12); }
button[kind="primary"]:disabled { background: #2a3040 !important; color: #8892a2 !important; cursor: not-allowed !important; }
[data-testid="stPopover"] button, button[kind="primary"], button[kind="secondary"] { white-space: nowrap; }
.act-note { color: #8892a2; font-size: .82rem; line-height: 1.35; }
.act-err { color: #ec6a6a; font-size: .82rem; line-height: 1.35; }
/* parameter grid: every label gets the height of two lines, so wrapped and unwrapped titles line up */
.st-key-params [data-testid="stWidgetLabel"] { min-height: 2.6rem; display: flex; align-items: flex-end; }
/* sidebar: long job titles stay on one line and fade out */
.side-title { white-space: nowrap; overflow: hidden; color: #b4bcc9; font-size: .85rem;
  -webkit-mask-image: linear-gradient(to right, #000 78%, transparent); mask-image: linear-gradient(to right, #000 78%, transparent); }
.side-state { font-size: .85rem; }
.side-note { color: #8892a2; font-size: .78rem; margin: .1rem 0; }
/* left navigation (Dashboard style): brand, section headings, one full-width entry per page, the active one highlighted */
section[data-testid="stSidebar"] { background: #171a21 !important; border-right: 1px solid #000; }
.nav-brand { display: flex; align-items: center; gap: .55rem; font-weight: 700; color: #fff; line-height: 1.25; font-size: .95rem;
  padding: .2rem 0 .7rem; border-bottom: 1px solid #333a4b; margin-bottom: .2rem; }
.nav-brand .nav-icon { font-size: 1.5rem; }
.navsec { font-size: .68rem; font-weight: 700; letter-spacing: .14em; color: #8892a2; padding: .6rem .2rem .15rem; line-height: 1.2; }
div[class*="st-key-nav-"] button, div[class*="st-key-navon-"] button { justify-content: flex-start !important; background: transparent !important;
  border: 0 !important; color: #b4bcc9 !important; font-weight: 500 !important; padding: .45rem .7rem !important; min-height: 0 !important; }
div[class*="st-key-nav-"] button:hover { color: #eef1f5 !important; background: #1f2430 !important; }
div[class*="st-key-navon-"] button { color: #fff !important; background: #1d3a5c !important; box-shadow: inset 3px 0 0 #4aa8ff; }
div[class*="st-key-nav-"] button > div, div[class*="st-key-navon-"] button > div { justify-content: flex-start !important; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .3rem; }
section[data-testid="stSidebar"] [data-testid="stMarkdown"], section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
/* the current job sits at the bottom of the navigation */
[data-testid="stSidebarUserContent"] { min-height: calc(100vh - 2.5rem); display: flex; flex-direction: column; padding-bottom: 1rem !important; }
[data-testid="stSidebarUserContent"] > div:first-child { flex: 1; display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] > div:first-child > [data-testid="stVerticalBlock"] { flex: 1; }
[data-testid="stLayoutWrapper"]:has(> .st-key-side-status), .st-key-side-status { margin-top: auto !important; }
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


def plain(text):
    """Problem texts may contain `code` marks; the inline hints are plain HTML."""
    import html
    return html.escape(str(text).replace("`", ""))


def action_row(label, key, problems, extra=None):
    """A start button with its hint on the same line, to its right: blue when it can start, locked with the reasons in
    red otherwise; while jobs run, the hint says where the new one will queue. Returns True when clicked."""
    c1, c2 = st.columns([2.2, 5], vertical_alignment="center")
    with c1:
        clicked = st.button(start_label(label), type="primary", disabled=bool(problems), key=key, width="stretch")
    with c2:
        if problems:
            st.markdown(f'<span class="act-err">無法開始：{"；".join(plain(p) for p in problems)}</span>', unsafe_allow_html=True)
        else:
            notes = [extra] if extra else []
            active, waiting = jobs.active_job(), jobs.waiting_jobs()
            if active or waiting:
                notes.append(f"目前有工作在跑：這個會排第 {len(waiting) + 1} 個，前面還有 {(1 if active else 0) + len(waiting)} 個；"
                             "關掉 ML UI 也會照順序繼續（前一個失敗或取消也一樣）")
            if notes:
                st.markdown(f'<span class="act-note">{"。".join(plain(n) for n in notes)}</span>', unsafe_allow_html=True)
    return clicked


def card(key, title=None):
    """A bordered card like the Dashboard's panels."""
    c = st.container(border=True, key=f"card-{key}")
    if title:
        c.markdown(f"### {title}")
    return c


def start_job(kind, title, spec):
    try:
        job_id = jobs.start(kind, title, spec)
        st.session_state["job-select"] = job_id  # the 工作 tab follows the new job
        pos = jobs.queue_position(job_id)
        st.session_state["job-started"] = f"已加入排隊（第 {pos} 個），會在前面的工作結束後自動開始。" if pos else f"工作已開始：進度在左側導覽最下方與「{TAB_QUEUE}」頁。"
        st.rerun()
    except (RuntimeError, ValueError, TimeoutError) as e:
        st.error(str(e))


def start_label(text):
    """The start buttons say 加入排隊 while another job runs: the new one waits for its turn."""
    return "加入排隊" if jobs.active_job() or jobs.waiting_jobs() else text


def pending_output(out_rel):
    """True when a waiting / starting / running job will write this output (two jobs must not write the same file)."""
    want = out_rel.replace("\\", "/")
    return any(str(j.get("spec", {}).get("out", "")).replace("\\", "/") == want
               for j in jobs.list_jobs() if j["state"] in ("waiting",) + jobs.BUSY)


def progress_of(job, evs):
    """(fraction, text) for any job kind, or None while nothing is known yet."""
    steps = [e for e in evs if e["stage"] in ("iteration", "epoch", "games")]
    if not steps:
        if any(e["stage"] == "publish" for e in evs):
            return None, "發佈 Runner 中（C# 原始碼比發佈版新）…"
        return None, "讀取資料中…" if job["kind"].startswith("train") else "啟動中…"
    last = steps[-1]
    if last["stage"] == "games":
        n, total = last["done"], last["total"]
        return n / max(1, total), f"{n:,}/{total:,} 局"
    n = last.get("iteration") or last.get("epoch")
    total = last.get("total") or n
    unit = "棵樹" if last["stage"] == "iteration" else "epoch"
    return min(1.0, n / max(1, total)), f"{n}/{total} {unit}（提早停止可能更早結束）"


def watch_states(all_jobs):
    """Fragments refresh alone; when any job changes state, rerun the whole page (start buttons, lists).

    Also the queue's safety net: a job that died without handing over (machine asleep, killed) leaves waiting jobs
    behind; start the next one."""
    if not any(j["state"] in jobs.BUSY for j in all_jobs) and any(j["state"] == "waiting" for j in all_jobs):
        try:
            jobs.start_next()
        except TimeoutError:
            pass
    signature = tuple((j["id"], j["state"]) for j in all_jobs)
    if st.session_state.get("job-signature") not in (None, signature):
        st.session_state["job-signature"] = signature
        st.rerun(scope="app")
    st.session_state["job-signature"] = signature


@st.fragment(run_every=2)
def sidebar_status():
    import html
    all_jobs = jobs.list_jobs()
    watch_states(all_jobs)
    active, waiting = jobs.active_job(), jobs.waiting_jobs()
    st.markdown('<div class="navsec">目前工作</div>', unsafe_allow_html=True)
    if active:
        st.markdown(f'<div class="side-title" title="{html.escape(active["title"])}">{html.escape(active["title"])}</div>',
                    unsafe_allow_html=True)
        frac, text = progress_of(active, jobs.events(active["id"]))
        lost = active["state"] == "lost"
        c1, c2 = st.columns([3, 1.3], vertical_alignment="bottom")
        if lost:
            c1.markdown('<div class="side-state lost">失聯：程序還在，但沒有回報；排隊暫停</div>', unsafe_allow_html=True)
        else:
            c1.progress(frac or 0.0, text=text)
        if c2.button("結束" if lost else "取消", key=f"stop-side-{active['id']}", width="stretch",  # stop-: red (CSS)
                     help=LOST_TEXT if lost else None):
            jobs.cancel(active["id"])
    else:
        st.markdown('<div class="side-note">沒有正在執行的工作</div>', unsafe_allow_html=True)
    if waiting:
        st.markdown(f'<div class="side-note">還有 {len(waiting)} 項排隊中</div>', unsafe_allow_html=True)


QUEUE_STATE = {"running": ("正在跑", "#4aa8ff"), "queued": ("啟動中", "#4aa8ff"), "waiting": ("排隊中", "#e0a410"),
               "done": ("已完成", "#3fa83f"), "failed": ("失敗", "#ec6a6a"), "cancelled": ("已取消", "#8892a2"),
               "interrupted": ("中斷", "#ec6a6a"), "lost": ("失聯", "#e8672f")}


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


def elapsed_text(job):
    started, finished = _epoch(job.get("started")), _epoch(job.get("finished"))
    if job["state"] == "waiting":
        return "已等 " + _duration(time.time() - job.get("createdEpoch", time.time()))
    if started is None:
        return "—"
    return _duration((finished or time.time()) - started)


def remark(job, col):
    """備註 column: errors collapsed, otherwise a one-line result."""
    state, result = job["state"], job.get("result") or {}
    if state == "failed":
        with col.expander("錯誤訊息", expanded=False):
            st.markdown(f'<span class="act-err" style="overflow-wrap:anywhere">{plain(scrub(job.get("error", "")))[:600]}</span>', unsafe_allow_html=True)
            st.caption("完整紀錄：下方「工作詳細」選這個工作。")
    elif state == "interrupted":
        col.caption("程序已不在（電腦睡眠、關機或被終止）")
    elif state == "lost":
        col.markdown('<span class="act-note" style="color:#e8672f">程序還在但沒有回報，排隊暫停中</span>',
                     unsafe_allow_html=True)
    elif state == "cancelled" and result.get("summary"):
        col.caption(scrub(result["summary"])[:120])
    elif state == "done" and job["kind"] == "match" and result.get("match"):
        m = result["match"]
        col.caption(f"勝率 {m['winShare']:.1%} ± {m['winShareCi95']:.1%}（{m['games']} 局），已記到模型")
    elif state == "done" and job["kind"].startswith("train") and result.get("validation"):
        col.caption(f"R² {result['validation']['r2']:.3f} → {rel(result['model'])}")
    elif state == "done" and job["kind"] == "dump" and result.get("rows"):
        col.caption(f"{result['games']:,} 局、{result['rows']:,} 列")
    elif state == "waiting":
        col.caption(f"排第 {jobs.queue_position(job['id'])} 個")


@st.fragment(run_every=2)
def queue_page():
    all_jobs = jobs.list_jobs()
    if not all_jobs:
        st.caption("還沒有工作。")
        return
    active, waiting = jobs.active_job(), jobs.waiting_jobs()
    done = [j for j in all_jobs if j["state"] not in ("waiting",) + jobs.BUSY][:40]
    ordered = ([active] if active else []) + waiting + done
    with card("queue", "工作列表"):
        st.caption("一次跑一個，依加入的順序；關掉 ML UI 也會繼續，前一個失敗或取消也會接著跑。最多列出最近 40 個已結束的工作。")
        widths = [3.8, 1, 1.25, 2, 2.6, 1.45]
        with st.container(key="qhead"):
            head = st.columns(widths)
            for c, t in zip(head, ["名稱", "狀態", "經過時間", "進度", "備註", "操作"]):
                c.markdown(f"**{t}**")
        for job in ordered:
            # one framed row per job; the key carries the state for the coloured left edge (CSS st-key-qrow-<state>)
            cols = st.container(key=f"qrow-{job['state']}-{job['id']}").columns(widths, vertical_alignment="center")
            cols[0].markdown(f"{plain(job['title'])}  \n<span class='act-note'>{KIND_TEXT.get(job['kind'], job['kind'])}・{(job.get('created') or '').replace('T', ' ').rstrip('Z')} UTC</span>",
                             unsafe_allow_html=True)
            text, color = QUEUE_STATE.get(job["state"], (job["state"], "#8892a2"))
            cols[1].markdown(f"<span style='color:{color};font-weight:600'>{text}</span>", unsafe_allow_html=True)
            cols[2].markdown(elapsed_text(job))
            if job["state"] in ("queued", "running"):
                frac, ptext = progress_of(job, jobs.events(job["id"]))
                cols[3].progress(frac or 0.0, text=ptext)
            elif job["state"] == "done":
                cols[3].progress(1.0)
            else:
                cols[3].markdown("—")
            if job["state"] in jobs.BUSY:
                if cols[5].button("強制結束" if job["state"] == "lost" else "取消", key=f"stop-q-{job['id']}", width="stretch"):
                    jobs.cancel(job["id"])
            elif job["state"] == "waiting":
                if cols[5].button("移出佇列", key=f"q-dequeue-{job['id']}", width="stretch"):
                    jobs.cancel(job["id"])
                    st.rerun(scope="app")
            remark(job, cols[4])
    with st.expander("工作詳細（紀錄、驗證 loss 曲線、結果）", expanded=False):
        # the label carries no state: the dropdown does not refresh the text of an option that is already shown
        labels = {j["id"]: f"{j['title']}（{j.get('created', '').replace('T', ' ').rstrip('Z')} UTC）" for j in ordered}
        if st.session_state.get("job-select") not in labels:
            st.session_state.pop("job-select", None)
        job_id = st.selectbox("工作", list(labels), format_func=labels.get, key="job-select")
        job_detail(job_id)


def job_detail(job_id):
    job = jobs.read_job(job_id)
    if job is None:  # its folder was removed meanwhile
        st.caption("這個工作的紀錄已經不在了。")
        return
    state = job["state"]
    evs = jobs.events(job_id)
    frac, text = progress_of(job, evs)
    if state == "waiting":
        frac, text = None, f"排隊中（第 {jobs.queue_position(job_id)} 個），前面的工作結束後自動開始"
    left, right = st.columns([2, 1])
    with left:
        if state == "waiting":
            st.info(text)
        elif frac is not None:
            st.progress(frac, text=f"{STATE_TEXT.get(state, state)}：{text}")
        elif state in ("queued", "running"):
            st.info(text)
        steps = [e for e in evs if e["stage"] in ("iteration", "epoch")]
        if steps:
            curve = pd.DataFrame({"步": [e.get("iteration") or e.get("epoch") for e in steps],
                                  "驗證 loss（交叉熵）": [e["validLoss"] for e in steps]}).set_index("步")
            st.line_chart(curve, height=220)
    with right:
        st.markdown(f"**種類**：{KIND_TEXT.get(job['kind'], job['kind'])}")
        st.markdown(f"**狀態**：{STATE_TEXT.get(state, state)}")
        loaded = next((e for e in evs if e["stage"] == "loaded"), None)
        if loaded:
            st.markdown(f"**資料**：{loaded['rows']:,} 列（驗證 {loaded['validRows']:,}）")
        if job.get("started"):
            st.markdown(f"**開始**：{job['started']}")
        if job.get("finished"):
            st.markdown(f"**結束**：{job['finished']}")
        if state == "lost":
            st.warning(LOST_TEXT)
        if state in jobs.BUSY:
            if st.button("強制結束這個工作" if state == "lost" else "取消這個工作", key=f"stop-detail-{job_id}"):
                jobs.cancel(job_id)
            st.caption("產生資料取消時，已完成的局數會保留（Windows 除外）；訓練取消不會留下模型；對戰取消不會記到模型。排隊中的下一個工作會接著開始。")
        if state == "waiting":
            if st.button("移出佇列", key=f"dequeue-{job_id}"):
                jobs.cancel(job_id)
        if state == "failed":
            st.error(scrub(job.get("error", "")))
        if state == "interrupted":
            st.warning("程序已不在（電腦睡眠、關機或被終止）。")
    result = job.get("result") or {}
    if state == "done" and job["kind"].startswith("train"):
        v = result["validation"]
        c1, c2, c3 = st.columns(3)
        c1.metric("驗證交叉熵", f"{v['crossEntropy']:.4f}")
        c2.metric("驗證 MSE", f"{v['mse']:.4f}", help=f"常數基準 {v['constantMse']:.4f}")
        c3.metric("R²", f"{v['r2']:.3f}")
        st.success(f"模型已存到 `{rel(result['model'])}`。下一步到「{TAB_MATCH}」和原版 MCTS 對打：真正的判準是勝率。")
    if job["kind"] == "dump" and state in ("done", "cancelled") and result.get("rows"):
        st.success(f"{'已取消，保留' if state == 'cancelled' else '完成'}：{result['games']:,} 局、{result['rows']:,} 列 → `{rel(result['output'])}`。可以到「{TAB_TRAIN}」頁勾選。")
    if job["kind"] == "match" and state == "done" and result.get("match"):
        m = result["match"]
        st.success(f"勝率 {m['winShare']:.1%} ± {m['winShareCi95']:.1%}（{m['games']} 局），已記到模型的 `.meta.json`。結果檔 `{rel(result['output'])}` 也可以在 Dashboard 打開。")
        grid(pd.DataFrame([{"座位": "價值模型 MCTS", "勝率": m["winShare"], "平均分": m["avgScore"]}] +
                                  [{"座位": o["seatId"] if o["strategy"] != "mcts" else ("原版 MCTS" if not o.get("valueModel") else "MCTS＋模型"),
                                    "勝率": o["winShare"], "平均分": o["avgScore"]} for o in m["others"]]),
                     hide_index=True, column_config={"勝率": st.column_config.NumberColumn(format="percent"),
                                                     "平均分": st.column_config.NumberColumn(format="%.1f")})
    with st.expander("紀錄（最後 40 行）", expanded=state == "failed"):
        st.code(scrub(jobs.log_tail(job_id)) or "（空的）", language=None)


# ---------------------------------------------------------------- 資料

def safe_name(name):
    return bool(name) and not any(c in name for c in '/\\:*?"<>| ')


def read_config(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def models_for(players):
    """Models with metadata for this player count."""
    out = []
    for p in model_files():
        meta = model_meta(p)
        if meta and meta.get("players") == players:
            out.append(p)
    return out


def write_config(path, cfg):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


# rule-based needs params.profile and is the same as the named strategies: not offered
_HIDDEN_STRATEGIES = {"rule-based"}
STRATEGY_TEXT = {
    "random": "完全隨機", "guided-random": "依動作種類加權的隨機", "mcts": "MCTS 樹搜尋（慢）",
    "corn-shipper": "玉米出貨", "corn-to-premium": "玉米轉菸草／咖啡", "harbor-rush": "港口流", "build-first": "建築流",
    "cheap-engine": "便宜引擎流", "wharf-rush": "私船流", "wharf-premium": "私船＋高價貨", "corn-monopoly": "玉米壟斷（搗亂）",
    "corn-monopoly-tiles": "只搶玉米種植園", "corn-monopoly-hoard": "只囤玉米",
}


@st.cache_data(show_spinner=False)
def strategy_names(mtime):
    """Registered strategies, read from the engine's registry (so the list never drifts from what the Runner accepts)."""
    path = os.path.join(ROOT, "Engine", "Strategies", "StrategyRegistry.cs")
    try:
        with open(path, encoding="utf-8") as f:
            names = re.findall(r'^\s*\["([a-z0-9-]+)"\]\s*=', f.read(), re.MULTILINE)
    except OSError:
        names = []
    names = [n for n in dict.fromkeys(names) if n not in _HIDDEN_STRATEGIES]
    return names or sorted(STRATEGY_TEXT)


def all_strategies():
    path = os.path.join(ROOT, "Engine", "Strategies", "StrategyRegistry.cs")
    return strategy_names(os.path.getmtime(path) if os.path.exists(path) else 0)


def parse_params(text):
    """'name=value, name=value' -> dict (numbers become numbers, like the Dashboard's parameter boxes). Raises ValueError."""
    out = {}
    for part in re.split(r"[,;]", text or ""):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"「{part}」格式應為 名稱=值")
        k, v = (x.strip() for x in part.split("=", 1))
        if not k or not v:
            raise ValueError(f"「{part}」格式應為 名稱=值")
        try:
            num = float(v)
            out[k] = int(num) if num.is_integer() and "." not in v else num
        except ValueError:
            out[k] = v
    return out


DEFAULT_CUSTOM = {4: ["cheap-engine", "build-first", "harbor-rush", "corn-to-premium"], 3: ["cheap-engine", "build-first", "harbor-rush"]}


def custom_seats(players):
    """One row per seat: strategy + its parameters. Returns (seats for the config, problems)."""
    names = all_strategies()
    seats, problems = [], []
    model_names = ["（不用，隨機 rollout）"] + [os.path.basename(p) for p in models_for(players)]
    for i in range(players):
        default = DEFAULT_CUSTOM[players][i] if DEFAULT_CUSTOM[players][i] in names else names[0]
        c1, c2 = st.columns([2, 5])
        strat = c1.selectbox(f"座位 {i + 1}", names, index=names.index(default), key=f"cu-s{i}",
                             format_func=lambda n: f"{n}（{STRATEGY_TEXT[n]}）" if n in STRATEGY_TEXT else n)
        with c2:
            if strat == "mcts":
                m1, m2, m3 = st.columns(3)
                sims = m1.number_input("模擬次數", value=100, min_value=1, step=50, key=f"cu-sims{i}")
                model = m2.selectbox("價值模型", model_names, key=f"cu-model{i}")
                leaf = m3.number_input("leafRollout", value=20 if model != model_names[0] else 0, min_value=0, step=5, key=f"cu-leaf{i}")
                params = {"simulations": int(sims)}
                if model != model_names[0]:
                    params["valueModel"] = rel(model_path(model))
                    if leaf:
                        params["leafRollout"] = int(leaf)
            else:
                text = st.text_input("參數（選填，名稱=值，逗號分隔）", key=f"cu-p{i}", placeholder="例如 buildThreshold=3.5")
                try:
                    params = parse_params(text)
                except ValueError as e:
                    problems.append(f"座位 {i + 1} 的參數：{e}")
                    params = {}
        seats.append({"id": f"{strat}-{i}", "strategy": strat, "params": params})
    return seats, problems


def tracked_by_git(paths):
    """Which of these files git tracks (built-in configs); empty when git is not available."""
    import subprocess
    try:
        out = subprocess.run(["git", "ls-files", "--", *[rel(p) for p in paths]], cwd=ROOT, capture_output=True, text=True, timeout=10)
        return set(out.stdout.split())
    except (OSError, subprocess.SubprocessError):
        return set()


def config_rows():
    """The data configs: built-in ml/data-configs, then local ml/local/data-configs."""
    rows = []
    files = sorted(glob.glob(os.path.join(ROOT, "ml", "data-configs", "*.json"))) + sorted(glob.glob(os.path.join(LOCAL_CONFIGS, "*.json")))
    for c in files:
        cfg = read_config(c)
        if cfg:
            rows.append({"設定檔": rel(c), "位置": "本機" if os.path.dirname(os.path.abspath(c)) == os.path.abspath(LOCAL_CONFIGS) else "內建",
                         "人數": cfg.get("players"), "局數": cfg.get("games"), "種子": cfg.get("seed"),
                         "座位": "、".join(s.get("strategy", "") for s in cfg.get("seats", []))})
    return rows


def config_table(rows):
    """All data configs with checkboxes for deleting (inside the 管理設定檔 expander)."""
    picked = grid(pd.DataFrame(rows).set_index("設定檔"), on_select="rerun", selection_mode="multi-row", width="stretch", key=f"cfg-table-{delete_gen()}")
    chosen = [rows[i]["設定檔"] for i in picked.selection.rows]
    c1, c2 = st.columns([4, 2.2], vertical_alignment="center")
    tracked = tracked_by_git(chosen) if chosen else set()
    c1.caption("勾選左側方格可以刪除設定檔。" + (f"其中 {len(tracked)} 個是 repo 內建的（git 追蹤中）：刪掉後可以用 git 還原。" if tracked else ""))
    with c2:
        delete_button("del-configs", f"🗑 刪除勾選（{len(chosen)}）", [absolute(c) for c in chosen], busy=busy_files("config"))


def data_tab():
    st.caption("用 Runner 打完整局並抽樣局面，寫到 `results/ml/`。第一次（或 C# 程式改過後）會先自動發佈 Runner（需要 .NET 8 SDK）。")
    stamp = datetime.datetime.now().strftime("%m%d-%H%M")
    custom_problems = []
    with card("data-source", "1. 採樣來源模型"):
        mode = st.radio("採樣來源模型", ["設定檔（手寫策略、隨機）", "自訂組合（自己選每個座位的策略）", "模型自我對戰（MCTS＋價值模型）"],
                        horizontal=True, label_visibility="collapsed")
        if mode.startswith("設定檔"):
            rows = config_rows()
            if not rows:
                st.info("沒有設定檔。用「自訂組合」新增一個。")
                return
            by_name = {r["設定檔"]: r for r in rows}
            config = st.selectbox("用哪個設定檔", list(by_name),
                                  format_func=lambda c: f"{c}（{by_name[c]['人數']} 人局：{by_name[c]['座位']}）")
            with st.expander(f"管理設定檔（全部 {len(rows)} 個；勾選後可以刪除）"):
                config_table(rows)
            cfg = read_config(absolute(config))
            default_games, default_seed = int(cfg.get("games", 20000)), int(cfg.get("seed", 1))
            default_rate = 0.05 if any(s_.get("strategy") == "mcts" for s_ in cfg.get("seats", [])) else 0.01
            default_name = os.path.basename(config)[:-5]
            title_kind = "設定檔"
        elif mode.startswith("自訂"):
            st.caption("每局就是你選的這幾個策略互打；座位順序每局隨機重排，所以每個策略都會坐到每個位置。"
                       "「新增設定」只把組合存成 `ml/local/data-configs/<名稱>.json`（本機，不進 git；之後在「設定檔」選它）；「開始產生資料」會存設定並開始。")
            players = st.radio("人數", [4, 3], horizontal=True, format_func=lambda n: f"{n} 人局", key="cu-players")
            seats, custom_problems = custom_seats(players)
            has_mcts = any(s_["strategy"] == "mcts" for s_ in seats)
            default_games, default_seed = (2000 if has_mcts else 20000), int(datetime.datetime.now().strftime("%m%d%H"))
            default_rate = 0.05 if has_mcts else 0.01
            if has_mcts:
                st.caption("有 MCTS 座位會慢很多（4 核心、100 次模擬大約每局 1～2 秒）；手寫策略與隨機玩家每秒可打上千局。")
            default_name = f"{players}p-custom-{stamp}"
            title_kind = "自訂：" + "、".join(s_["strategy"] for s_ in seats)
        else:
            players = st.radio("人數", [4, 3], horizontal=True, format_func=lambda n: f"{n} 人局", key="sp-players")
            cands = models_for(players)
            if not cands:
                st.info(f"還沒有 {players} 人局的模型（要有 `.meta.json`）。先用設定檔的資料訓練一個。")
                return
            model = st.selectbox("用哪個模型", [os.path.basename(p_) for p_ in cands], index=len(cands) - 1)
            c1, c2 = st.columns(2)
            sims = c1.number_input("每步模擬次數", value=100, min_value=1, step=50, help="自我對戰用較少的次數換局數（v2 用 100）")
            leaf = c2.number_input("leafRollout（估值前先打幾步）", value=20, min_value=0, step=5)
            default_games, default_seed, default_rate = 4000, int(datetime.datetime.now().strftime("%m%d%H")), 0.05
            default_name = f"{players}p-selfplay-{model.rsplit('.', 1)[0].replace(f'{players}p-', '')}-{stamp}"
            title_kind = f"自我對戰 {model}"

    with card("data-run", "2. 局數設定"):
        c1, c2, c3, c4 = st.columns(4)
        # the defaults come from the chosen config: its name is part of the keys, so picking another config reloads them
        kk = mode[:2] + (config if mode.startswith("設定檔") else "")
        games = c1.number_input("局數", value=default_games, min_value=1, step=1000, key=f"games-{kk}")
        seed = c2.number_input("種子", value=default_seed, step=1, key=f"seed-{kk}")
        rate = c3.number_input("抽樣率（每個決策被抽到的機率）", value=default_rate, min_value=0.0001, max_value=1.0, format="%g", key=f"rate-{kk}")
        threads = c4.number_input("執行緒（0＝全部）", value=0, min_value=0, step=1, key=f"threads-{mode[:2]}")
        if mode.startswith("模型"):
            st.caption(f"參考：4 核心、100 次模擬、leafRollout 20 約 1 局／秒（{games:,} 局約 {games / 3600:.1f} 小時）。")
        name = st.text_input("輸出名稱（results/ml/<名稱>.bin）", value=default_name).strip()
        out = os.path.join(jobs.results_dir(), "ml", name + ".bin")
        exists = os.path.exists(out)
        overwrite = st.checkbox(f"覆寫已存在的 `{name}.bin`") if exists else True
        writes_config = not mode.startswith("設定檔")
        config_taken = writes_config and safe_name(name) and any(os.path.exists(os.path.join(d, name + ".json"))
                                                                  for d in (os.path.join(ROOT, "ml", "data-configs"), LOCAL_CONFIGS))
        name_problems = [p_ for p_ in [None if safe_name(name) else "名稱不能空白或含路徑符號、空白",
                                       f"已經有同名的設定檔 {name}.json，換一個名稱（不覆蓋既有設定）" if config_taken else None] if p_]
        problems = name_problems + [p_ for p_ in [None if overwrite else "資料已存在（要覆寫請勾選）",
                                                  "排隊中或執行中的工作已經會寫這個檔名，換一個名稱" if pending_output(rel(out)) else None] if p_] + custom_problems

        def new_config():
            if mode.startswith("自訂"):
                return {"schemaVersion": 1, "name": name, "players": players, "games": int(games), "seed": int(seed),
                        "seatOrder": "random", "seats": seats, "output": {"perGameRecords": False}}
            return {"schemaVersion": 1, "name": name, "players": players, "games": int(games), "seed": int(seed), "seatOrder": "random",
                    "seats": [{"id": f"m{i}", "strategy": "mcts",
                               "params": {"simulations": int(sims), "valueModel": rel(model_path(model)), "leafRollout": int(leaf)}}
                              for i in range(players)],
                    "output": {"perGameRecords": False}}

        # what this run would produce, by recipe: compared with what already exists under this name and under other names
        eff = {**cfg, "games": int(games), "seed": int(seed)} if mode.startswith("設定檔") else new_config()
        new_recipe = fingerprint.planned_dump_recipe(eff, float(rate))
        new_fp = fingerprint.fingerprint(new_recipe)
        known = [d for d in list_dumps() if "_fp" in d]
        old_recipe = next((d["_recipe"] for d in known if d["path"] == rel(out)), None)
        same_name_notice("資料", exists, old_recipe, new_recipe, users=models_using(rel(out)) if exists else ())
        twins = [d["來源"] for d in known if d["_fp"] == new_fp and d["path"] != rel(out)]
        if twins:
            st.info("已經有相同配方（同樣的設定、種子、局數與抽樣率）的資料：" + "、".join(f"`{t}`" for t in twins)
                    + "。重跑只會得到同一份內容，通常不需要再產生。")
        if exists and reader_problem(rel(out)):
            problems.append(reader_problem(rel(out)))

        if mode.startswith("自訂"):
            save_problems = name_problems + custom_problems
            b1, b2 = st.columns([2.2, 5], vertical_alignment="center")
            with b1:
                save = st.button("新增設定", key="save-config", disabled=bool(save_problems), width="stretch")
            with b2:
                st.markdown('<span class="act-err">無法儲存：' + "；".join(plain(x) for x in save_problems) + "</span>" if save_problems
                            else f'<span class="act-note">只儲存成 ml/local/data-configs/{plain(name)}.json，不產生資料</span>', unsafe_allow_html=True)
            if save:
                write_config(os.path.join(LOCAL_CONFIGS, name + ".json"), new_config())
                st.session_state["job-started"] = f"已儲存 ml/local/data-configs/{name}.json：之後可以在「設定檔」選它。"
                st.rerun()

        if action_row("開始產生資料", "start-dump", problems):
            if mode.startswith("設定檔"):
                spec_config = config
            else:
                spec_config = rel(os.path.join(LOCAL_CONFIGS, name + ".json"))
                write_config(absolute(spec_config), new_config())  # kept with the other data configs: reusable and reproducible
            start_job("dump", f"資料（{title_kind}）→ {name}.bin", {"config": spec_config, "out": rel(out), "rate": float(rate),
                                                                  "games": int(games), "seed": int(seed), "threads": int(threads)})

    with card("data-list", "已有的資料"):
        dumps = [d for d in list_dumps() if "error" not in d and not d.get("writing")]
        if dumps:
            grid(table_view(dumps, "檔案"), hide_index=True, width="stretch")
            st.caption(f"要刪除資料，到「{TAB_TRAIN}」頁勾選後按刪除。")
        else:
            st.caption("還沒有資料。")


# ---------------------------------------------------------------- 對戰驗證

MATCH_TABLES = {
    "default": "對原版 MCTS（同桌另有手寫策略）",
    "hand": "對手寫策略（分析文件第 5 節那桌）",
}


def match_seats(table, players, model, sims, leaf, base_sims):
    me = {"id": "value", "strategy": "mcts", "params": {"simulations": sims, "valueModel": rel(model_path(model))}}
    if leaf:
        me["params"]["leafRollout"] = leaf
    hand = lambda name: {"id": name, "strategy": name, "params": {}}  # noqa: E731
    if table == "default":
        base = {"id": "mcts-default", "strategy": "mcts", "params": {"simulations": base_sims}}
        rest = ["cheap-engine", "build-first"] if players == 4 else ["cheap-engine"]
        return [me, base] + [hand(n) for n in rest]
    rest = ["corn-shipper", "corn-to-premium", "build-first"] if players == 4 else ["corn-shipper", "build-first"]
    return [me] + [hand(n) for n in rest]


def _match_body():
    st.caption("用 balanced 座位打一組對局，比較價值模型版 MCTS 的勝率；結果會記到模型的 `.meta.json`，也能在 Dashboard 打開。"
               "比較要做兩種：同模擬次數（模型有沒有更準），和約同時間（值不值得）：v2 的推論成本約讓 300 次模擬的時間只夠 180 次。")
    players = st.radio("人數", [4, 3], horizontal=True, format_func=lambda n: f"{n} 人局", key="m-players")
    cands = models_for(players)
    if not cands:
        st.info(f"還沒有 {players} 人局的模型。")
        return
    names = [os.path.basename(p) for p in cands]
    model = st.selectbox("模型", names, index=len(names) - 1, key="m-model")
    table = st.radio("對手", list(MATCH_TABLES), format_func=MATCH_TABLES.get, horizontal=True)
    c1, c2, c3, c4 = st.columns(4)
    sims = c1.number_input("模型版模擬次數", value=300, min_value=1, step=10)
    leaf = c2.number_input("leafRollout", value=0, min_value=0, step=5)
    base_sims = c3.number_input("原版 MCTS 模擬次數", value=300, min_value=1, step=10, disabled=table != "default")
    seed = c4.number_input("種子", value=9191, step=1)
    perm = 24 if players == 4 else 6
    c5, c6 = st.columns(2)
    games = c5.number_input(f"局數（{perm} 的倍數＝每種座位排列一樣多）", value=240 if table == "default" else 408, min_value=perm, step=perm)
    threads = c6.number_input("執行緒（0＝全部）", value=0, min_value=0, step=1, key="m-threads")
    seats = match_seats(table, players, model, int(sims), int(leaf), int(base_sims))
    st.caption("同桌：" + "、".join(("價值模型 MCTS" if s["id"] == "value" else "原版 MCTS" if s["strategy"] == "mcts" else s["strategy"]) for s in seats)
               + f"。參考：4 核心約 {int(games) * 0.6 / 60:.0f}～{int(games) * 1.2 / 60:.0f} 分鐘（依模擬次數）。")
    stem = model.rsplit(".", 1)[0]
    default_name = f"{stem}-s{int(sims)}{f'-leaf{int(leaf)}' if leaf else ''}-vs-{'default' if table == 'default' else 'hand'}{f'{int(base_sims)}' if table == 'default' and base_sims != 300 else ''}-seed{int(seed)}"
    name = st.text_input("名稱（設定檔 ml/local/matches/<名稱>.json、結果 results/ml/<名稱>.json）", value=default_name).strip()
    out = os.path.join(jobs.results_dir(), "ml", name + ".json")
    exists = os.path.exists(out)
    # recipe of this match (the value model counts by file content), compared with the result under this name and with
    # the matches already recorded for the model
    new_recipe = fingerprint.planned_match_recipe({"players": players, "games": int(games), "seed": int(seed),
                                                   "seatOrder": "balanced", "seats": seats})
    new_fp = fingerprint.fingerprint(new_recipe)
    old_recipe = None
    if exists:
        try:
            with open(out, encoding="utf-8") as f:
                old_recipe = fingerprint.result_recipe(json.load(f))
        except (OSError, ValueError, KeyError, TypeError):
            old_recipe = None
    same_name_notice("對戰結果", exists, old_recipe, new_recipe)
    done_meta = model_meta(model_path(model))
    twins = [m for m in (done_meta or {}).get("matches", []) if m.get("fingerprint") == new_fp and m.get("result") != rel(out)]
    if twins:
        st.info("這個模型已經有相同配方的對戰：" + "、".join(f"`{m['config']}`（勝率 {m['winShare']:.1%}）" for m in twins) + "。重跑只會得到同樣的結果。")
    overwrite = st.checkbox(f"覆寫已存在的結果 `{name}.json`") if exists else True
    problems = [p for p in [None if safe_name(name) else "名稱不能空白或含路徑符號、空白",
                            None if games % perm == 0 else f"局數要是 {perm} 的倍數",
                            None if overwrite else "結果已存在",
                            "排隊中或執行中的工作已經會寫這個結果檔，換一個名稱" if pending_output(rel(out)) else None] if p]
    if action_row("開始對戰", "start-match", problems):
        cfg = {"schemaVersion": 1, "name": name, "players": players, "games": int(games), "seed": int(seed),
               "seatOrder": "balanced", "seats": seats, "output": {"perGameRecords": False}}
        if threads:
            cfg["parallelism"] = {"maxDegree": int(threads)}
        config = rel(os.path.join(LOCAL_MATCHES, name + ".json"))
        write_config(absolute(config), cfg)
        start_job("match", f"對戰 {model}（{int(sims)} 次）{'vs 原版' if table == 'default' else 'vs 手寫'} → {name}",
                  {"config": config, "out": rel(out), "model": rel(model_path(model))})
    meta = model_meta(model_path(model))
    if meta and meta.get("matches"):
        st.markdown(f"**{model} 已有的對戰**")
        grid(matches_frame(meta, model_path(model)), hide_index=True, width="stretch",
                     column_config={"勝率": st.column_config.NumberColumn(format="percent"),
                                    "±95%": st.column_config.NumberColumn(format="percent"),
                                    "平均分": st.column_config.NumberColumn(format="%.1f")})


# ---------------------------------------------------------------- 模型清單

def models_table(paths):
    rows = []
    for p in paths:
        meta = model_meta(p)
        name = os.path.basename(p)
        if not meta:
            rows.append({"模型": name, "位置": place_of(p), "種類": "LightGBM" if p.endswith(".txt") else "MLP", "備註": "沒有 .meta.json"})
            continue
        best = best_vs_default(meta)
        v = meta.get("validation") or {}
        rows.append({
            "模型": name, "位置": place_of(p), "種類": KIND_TEXT.get(meta["kind"], meta["kind"]), "人數": meta["players"],
            "建立": (meta.get("created") or "（補寫）")[:16].replace("T", " "),
            "資料列數": sum(d["rows"] for d in meta["data"]),
            "自我對戰資料": "、".join(sorted({os.path.basename(m) for d in meta["data"] for m in d.get("valueModels", [])})),
            "R²": v.get("r2"), "交叉熵": v.get("crossEntropy"),
            "對戰場數": len(meta.get("matches", [])),
            "對原版 MCTS 最佳勝率": best["winShare"] if best else None,
            "hash": fingerprint.short(meta.get("fingerprint")) or "—",
            "版本狀態": version_text(model_stale(meta)) if meta.get("data") else "—",
            "備註": "參數為補寫" if "note" in meta.get("params", {}) else ("舊紀錄：沒有配方 hash" if not meta.get("fingerprint") else ""),
        })
    df = pd.DataFrame(rows)
    # text columns so that missing values read "—" instead of Streamlit's grey "None"
    fmt = {"R²": "{:.3f}", "交叉熵": "{:.4f}", "對原版 MCTS 最佳勝率": "{:.1%}", "資料列數": "{:,.0f}", "人數": "{:.0f}", "對戰場數": "{:.0f}"}
    for col, f in fmt.items():
        if col in df:
            df[col] = [f.format(v) if v is not None and v == v else "—" for v in df[col]]
    return df.fillna("")


def match_note(m, current_sha):
    """Why an old result may no longer describe the model / engine of today."""
    notes = []
    if m.get("modelSha256") and current_sha and m["modelSha256"] != current_sha:
        notes.append("模型檔已更新，這場是舊版模型打的")
    stale = entry_stale(m.get("rulesRevision", 1), m.get("ruleset"), m.get("revisions"),
                        [o.get("strategy") for o in m.get("others", [])] + ["mcts"])
    if stale:
        notes.append("舊版：" + "；".join(stale))
    return "；".join(notes)


def matches_frame(meta, model_file=None):
    current_sha = fingerprint.file_sha256(model_file) if model_file and os.path.exists(model_file) else None
    rows = []
    for m in meta.get("matches", []):
        rows.append({"設定": m.get("config"), "對手": describe_match(m), "局數": m["games"], "種子": m["seed"],
                     "勝率": m["winShare"], "±95%": m.get("winShareCi95"), "平均分": m["avgScore"],
                     "對手勝率": "、".join(f"{o['strategy'] if not o.get('valueModel') else 'MCTS＋模型'} {o['winShare']:.1%}" for o in m["others"]),
                     "紀錄": "本機" if m.get("local") else "正式", "hash": fingerprint.short(m.get("fingerprint")) or "—",
                     "備註": match_note(m, current_sha), "結果檔": m["result"]})
    return pd.DataFrame(rows)


def flat_params(meta):
    return {k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in (meta.get("params") or {}).items()}


def move_buttons(path):
    """設為正式模型 (local -> ml/models, then commit it) and 移到本機 (an official-folder model git does not track)."""
    name = os.path.basename(path)
    if place_of(path) == "本機":
        c1, c2 = st.columns([2.2, 5], vertical_alignment="center")
        with c1:
            with st.popover("設為正式模型", width="stretch"):
                st.markdown(f"把 `{name}`（連同 `.meta.json`、`.check.txt`）搬到 `ml/models/`。之後在 Visual Studio commit，才會進 git、別台電腦和 Claude 才看得到。"
                            "也請在 `docs/models.md` 的模型列表補一列。")
                if st.button("確定搬過去", type="primary", key=f"promote-{name}"):
                    try:
                        modelmeta.move_model(path, MODELS_DIR)
                        st.session_state["job-started"] = f"{name} 已設為正式模型（ml/models/）。"
                        st.cache_data.clear()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        c2.markdown('<span class="act-note">本機模型：只在這台電腦（ml/local/models/），不會進 git。</span>', unsafe_allow_html=True)
    elif not tracked_by_git([path]):
        c1, c2 = st.columns([2.2, 5], vertical_alignment="center")
        with c1:
            if st.button("移到本機", key=f"demote-{name}", width="stretch"):
                try:
                    modelmeta.move_model(path, LOCAL_MODELS)
                    st.session_state["job-started"] = f"{name} 已移到本機工作區（ml/local/models/）。"
                    st.cache_data.clear()
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        c2.markdown('<span class="act-note">這個模型在正式資料夾 ml/models/，但 git 沒有追蹤它（例如以前在 ML UI 訓練的）：'
                    "移到本機就不會再出現在 Visual Studio 的 Git 變更裡。</span>", unsafe_allow_html=True)


def model_detail(path):
    meta = model_meta(path)
    name = os.path.basename(path)
    move_buttons(path)
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
    mf = matches_frame(meta, path)
    if mf.empty:
        st.caption("還沒有對戰紀錄。")
    else:
        grid(mf, hide_index=True, width="stretch",
                     column_config={"勝率": st.column_config.NumberColumn(format="percent"),
                                    "±95%": st.column_config.NumberColumn(format="percent"),
                                    "平均分": st.column_config.NumberColumn(format="%.1f")})
        st.caption(f"結果檔可以在 Dashboard（{DASHBOARD_URL}）的「結果」「比較」頁打開。")

    left, right = st.columns(2)
    with left:
        st.markdown("**訓練參數**")
        grid(pd.DataFrame(list(flat_params(meta).items()), columns=["參數", "值"]).astype(str),
                     hide_index=True, width="stretch")
    with right:
        st.markdown("**驗證（各回合段）**")
        if v.get("byRound"):
            grid(pd.DataFrame(v["byRound"]).rename(columns={"rounds": "回合", "rows": "列數", "mse": "MSE"}),
                         hide_index=True, width="stretch")
        else:
            st.caption("沒有紀錄。")
        st.caption("驗證成績只是檢查訓練有沒有壞掉；資料分布不同時 R² 不能互相比較。")

    st.markdown("**訓練資料**")
    grid(pd.DataFrame([{"來源": d["source"], "局數": d["games"], "列數": d["rows"], "抽樣率": d["rate"],
                                "狀態": d["status"], "策略": "、".join(dict.fromkeys(s for s in d["strategies"] if s)),
                                "自我對戰模型": "、".join(os.path.basename(m) for m in d.get("valueModels", [])),
                                "hash": fingerprint.short(d.get("fingerprint")) or "—",
                                "版本": (fingerprint.rules_name(d.get("rulesRevision", 1), d.get("ruleset")) + "、"
                                         + "、".join(fingerprint.strategy_name(k, v) for k, v in (d.get("revisions") or {}).items())).rstrip("、"),
                                "檔案": d["path"]} for d in meta["data"]]),
                 hide_index=True, width="stretch")

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
            st.altair_chart(chart.properties(height=420), width="stretch")
        else:
            st.caption("只有 LightGBM 有（MLP 或補寫的 meta 沒有）。")
    env = meta.get("environment") or {}
    env_text = "環境未記錄" if "note" in env else "・".join(f"{k} {val}" for k, val in env.items())
    st.caption(f"特徵版本 {meta['featureVersion']}（{meta['featureCount']} 個）・建立 {meta.get('created') or '（補寫）'}・{env_text}"
               + (f"・配方 hash {fingerprint.short(meta['fingerprint'])}・規則版本 {fingerprint.rules_name(meta.get('rulesRevision', 1), (meta.get('data') or [{}])[0].get('ruleset'))}" if meta.get("fingerprint") else "・舊紀錄：沒有配方 hash"))
    stale = model_stale(meta)
    if stale:
        st.warning("這個模型的資料有些是用舊版規則或舊版策略產生的（" + "；".join(stale) + "）："
                   "它學到的是舊版下的局面，建議用目前的版本重新產生資料並重訓。")


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
    grid(pd.DataFrame(rows), hide_index=True, width="stretch")


def _models_body():
    paths = model_files()
    if not paths:
        st.info("還沒有模型（正式 ml/models/、本機 ml/local/models/ 都是空的）。")
        return
    table = models_table(paths)
    grid(table, hide_index=True, width="stretch")
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


def match_tab():
    with card("match", "對戰驗證：模型版 MCTS 上桌打一組對局"):
        _match_body()


def models_tab():
    with card("models", "模型（正式 ml/models/ ＋ 本機 ml/local/models/）"):
        _models_body()


# ---------------------------------------------------------------- hash 說明、版本控管

def _option_names(keys):
    return "、".join(f"{PARAM_HELP[k][0].split('（')[0]}（`{k}`）" if k in PARAM_HELP else f"`{k}`" for k in keys)


def hash_page():
    rev, now = fingerprint.current_rules_revision(), fingerprint.rules_name(fingerprint.current_rules_revision())
    with card("hash-what", "hash 是什麼"):
        st.markdown(
            "每份**資料**、每個**模型**、每場**對戰**都有一個 **hash**（SHA-256，畫面顯示前 8 碼）：把「決定結果的參數」整理成固定格式再算出來。"
            "引擎對設定與種子是確定的，所以**參數全部一樣，hash 才會一樣，重跑也只會得到同一份內容**；任何一個參數不同，hash 就不同。\n\n"
            "hash 只回答「是不是全部一樣」；「哪裡不一樣」由記下來的參數比出來（例如「局數：20,000 → 200,000」）。")
        st.caption("整理格式：參數名稱排序、`100` 和 `100.0` 視為相同、座位順序不分大小寫。計算在 `ml/fingerprint.py`。")
    with card("hash-data", "資料（.bin）的 hash"):
        st.markdown("**計入**")
        st.table(pd.DataFrame([
            ("人數、局數", "局數是實際打完的局數（中途取消的資料較少）"),
            ("種子、抽樣率、座位順序", "座位順序 random／balanced，不分大小寫"),
            ("每個座位的策略、**策略版本**與**完整參數**", "**依座位順序**：座位換位置，hash 就不同。參數是引擎實際使用的值：設定檔沒寫的參數，用該人數的預設值補上，所以改了預設值 hash 也會不同"),
            ("價值模型（自我對戰用）", "用**模型檔案的內容**（SHA-256），不是檔名：同名檔案被重訓覆寫後 hash 就變了"),
            ("最大回合數、每局最大決策數、自動跳過唯一合法動作", "設定檔的 limits、options；沒寫就用引擎預設值"),
            ("規則集與規則版本", f"目前 {now}（規則集 base、修訂 {rev}）；見「版本控管」頁"),
            ("變體與變體選項", "預留給以後的自訂規則（例如起始金錢兩倍），目前一律是「無」"),
            ("hash 格式版本", f"目前 {fingerprint.HASH_FORMAT}；配方的結構改了才會變（所有 hash 會一起變）"),
            ("特徵版本、資料格式版本", "特徵清單或 .bin 排列改了，資料就不一樣"),
        ], columns=["參數", "說明"]).set_index("參數"))
        st.markdown("**不計入**")
        st.table(pd.DataFrame([
            ("檔名、輸出名稱、設定檔名稱", "改名字不會讓資料變成另一份"),
            ("座位 id", "只是標籤，座位的策略與參數才算"),
            ("執行緒數", "引擎保證結果與執行緒數無關"),
            ("引擎版本、git commit、產生時間", "只用來追溯（記在 .bin.json），不進 hash"),
        ], columns=["參數", "原因"]).set_index("參數"))
    with card("hash-model", "模型的 hash"):
        st.markdown("**計入**")
        st.table(pd.DataFrame([
            ("種類", "LightGBM 或 MLP"),
            ("hash 格式版本", ""),
            ("特徵版本", ""),
            ("每份訓練資料的 hash（排序後）", "用資料的 hash，不是檔名：資料被覆寫或換了，模型的 hash 就不同；勾選順序不影響"),
            ("LightGBM 訓練參數", _option_names(fingerprint.LGBM_OPTIONS)),
            ("MLP 訓練參數", _option_names(fingerprint.MLP_OPTIONS) + "；訓練引擎與裝置用**實際解析後**的值（auto 會換成 torch／numpy、cuda／cpu）"),
        ], columns=["參數", "說明"]).set_index("參數"))
        st.markdown("**不計入**")
        st.table(pd.DataFrame([
            ("模型名稱", "改名字不會讓模型變成另一個"),
            ("執行緒數（`threads`）", "LightGBM 樹的結果與執行緒數無關（有測試驗證）"),
            ("套件版本（lightgbm、torch、numpy）、Python 版本、訓練時間", "記錄並顯示，但不進 hash"),
        ], columns=["參數", "原因"]).set_index("參數"))
        st.caption("新增訓練參數時必須同步 `fingerprint.LGBM_OPTIONS`／`MLP_OPTIONS`（測試會檢查）。早期補寫的模型沒有 hash，標「舊紀錄」。")
    with card("hash-match", "對戰結果的 hash"):
        st.markdown("與資料相同（人數、局數、種子、座位順序、每個座位的策略、策略版本與完整參數、價值模型的檔案內容、limits、options、規則集與規則版本、變體），"
                    "但**沒有**抽樣率與特徵版本。不計入：結果檔名、設定檔名稱、座位 id、執行緒數、引擎版本與 git commit。"
                    "每場對戰另外記下當時模型檔案的 hash：模型之後被覆寫，舊結果會標「模型檔已更新」。")
    with card("hash-versions", "規則版本、策略版本與預設值"):
        st.markdown(
            f"- **規則版本**（目前 {now}）：遊戲規則與亂數／種子衍生改了才加 1，所有資料都受影響。\n"
            "- **策略版本**（例如 `harbor-rush-v1`）：每個策略自己的決策邏輯改了才加 1，**只有用到這個策略的資料**受影響；"
            "MCTS 的版本也包含它的 rollout 策略與價值模型推論程式。\n"
            "- **預設值**：改策略的預設參數**不需要**加版本。引擎會把每個座位實際使用的完整參數（預設值填好）記進資料與結果檔，"
            "hash 用的就是它，所以預設值一改，hash 自然不同。\n"
            "- **舊檔案**：引擎開始記錄完整參數以前的資料與結果檔，用凍結的預設值表（`ml/strategy-params.legacy.json`，"
            "策略 v1、規則 base-v1 當時的預設值）補算；之後的預設值改動不會影響它們。新的執行則用目前的預設值表"
            "（`ml/strategy-params.json`，由引擎產生、測試檢查與程式一致）預測 hash。")
    with card("hash-use", "hash 在 ML UI 裡怎麼用"):
        st.markdown(
            "- **同名檔案**：hash 相同→「完全相同，不需要覆寫」；不同→列出差異；資料被模型用過會列出是哪些模型。\n"
            "- **不同名但 hash 相同**：提示重複（避免同一份資料被勾兩次訓練，讓模型多看一次同樣的局面）。\n"
            f"- **舊版**：規則版本低於目前（{now}），或座位上的策略版本低於目前的資料與模型，「版本狀態」會寫「舊：…」，建議重新產生。\n"
            "- **排隊保護**：排隊中或執行中的工作要讀的檔案（訓練資料、對戰用的模型）不能被覆寫。")
    with card("hash-look", "查看某份資料或模型的配方"):
        dumps = [d for d in list_dumps() if "_fp" in d]
        choices = {f"資料　{d['來源']}": (d["_recipe"], d["_fp"]) for d in dumps}
        for mp in model_files():
            meta = model_meta(mp)
            if meta and meta.get("recipe"):
                choices[f"模型　{os.path.basename(mp)}"] = (meta["recipe"], meta["fingerprint"])
        if not choices:
            st.caption("還沒有資料或模型。")
            return
        pick = st.selectbox("選一份", list(choices), key="hash-look-pick")
        recipe, full = choices[pick]
        st.markdown(f"hash：`{full}`")
        st.json(recipe, expanded=2)


def versions_page():
    tracks, error = fingerprint.load_versions()
    if error:
        st.error(error)
        return
    with card("ver-now", "這份程式現在的版本"):
        c = st.columns(4)
        c[0].metric("規則版本", fingerprint.rules_name(fingerprint.current_rules_revision()))
        c[1].metric("引擎版本", fingerprint.current_engine_version())
        c[2].metric("特徵版本", str(fingerprint.current_feature_version()))
        c[3].metric("資料格式版本", str(fingerprint.current_format_version()))
        now = {"rules": str(fingerprint.current_rules_revision()), "engine": fingerprint.current_engine_version(),
               "features": str(fingerprint.current_feature_version()), "format": str(fingerprint.current_format_version())}
        stale = [t["title"] for t in tracks.values() if t["id"] in now and (t["entries"] or [{}])[0].get("version") != now[t["id"]]]
        if stale:
            st.warning("版本清單（docs/versions.json）和程式裡的版本號不一致：" + "、".join(stale) + "。請補上這個版本做了哪些修改。")
        st.caption("同一份清單 Dashboard 的「版本控管」頁也有。規則版本只管遊戲規則與亂數；每個策略另有自己的策略版本（本頁最下方）；"
                   "引擎版本給人看；hash 用規則版本、策略版本、特徵版本、資料格式版本判斷資料與模型是不是舊的。")
    for t in tracks.values():
        entries = t.get("entries", [])
        cur = entries[0]["version"] if entries else "?"
        with card(f"ver-{t['id']}", f"{t['title']}：{t['display'].replace('{version}', cur)}"):
            st.caption(f"來源：`{t['source']}`")
            st.markdown(t["meaning"])
            st.markdown(f"**什麼時候加**：{t['bump']}")
            for e in entries:
                commit = f"　commit `{e['commit'][:8]}`" if e.get("commit") else ""
                st.markdown(f"**{t['display'].replace('{version}', e['version'])}**　{e['date']}{commit}\n" + "\n".join(f"- {c}" for c in e["changes"]))
    (info, strategies), _ = fingerprint.load_versions(strategies=True)
    with card("ver-strategies", info.get("title", "策略版本")):
        st.markdown(info.get("meaning", ""))
        st.markdown(f"**什麼時候加**：{info.get('bump', '')}")
        rows, mismatch = [], []
        for t in strategies:
            e = (t.get("entries") or [{}])[0]
            code = fingerprint.current_strategy_revision(t["id"])
            if code is not None and str(code) != str(e.get("version")):
                mismatch.append(t["id"])
            rows.append({"策略": t["id"], "目前版本": fingerprint.strategy_name(t["id"], e.get("version", "?")), "日期": e.get("date", ""),
                         "commit": (e.get("commit") or "")[:8] or "—", "這個版本的修改": "；".join(e.get("changes", []))})
        if mismatch:
            st.warning("版本清單和程式裡的策略版本不一致：" + "、".join(mismatch) + "。")
        st.table(pd.DataFrame(rows).set_index("策略"))
        with st.expander("每個策略的完整歷史"):
            for t in strategies:
                for e in t.get("entries", []):
                    st.markdown(f"**{fingerprint.strategy_name(t['id'], e['version'])}**　{e['date']}\n" + "\n".join(f"- {c}" for c in e["changes"]))


# left navigation like the Dashboard: (id, title, icon, page function, section heading shown above it)
PAGES = [("data", TAB_DATA, "🎲", lambda: data_tab(), "流程"),
         ("train", TAB_TRAIN, "🧠", lambda: training_tab(), None),
         ("match", TAB_MATCH, "⚔️", lambda: match_tab(), None),
         ("models", TAB_MODELS, "📦", lambda: models_tab(), "管理"),
         ("queue", TAB_QUEUE, "🗂️", lambda: queue_page(), None),
         ("hash", "hash 說明", "🔑", lambda: hash_page(), "說明"),
         ("versions", "版本控管", "🏷️", lambda: versions_page(), None)]


def current_page():
    ids = [p[0] for p in PAGES]
    page = st.session_state.get("page") or st.query_params.get("page")
    return page if page in ids else ids[0]


def go(page):
    st.session_state["page"] = page
    st.query_params["page"] = page  # a reload stays on the same page


def sidebar_nav(page):
    st.markdown(f'<div class="nav-brand"><span class="nav-icon">🌱</span><span>Puerto Rico<br>Machine Learning</span></div>',
                unsafe_allow_html=True)
    for pid, title, icon, _, section in PAGES:
        if section:
            st.markdown(f'<div class="navsec">{section}</div>', unsafe_allow_html=True)
        # the active entry gets another key prefix (navon-) so the CSS can highlight it
        st.button(f"{icon} {title}", key=f"{'navon' if pid == page else 'nav'}-{pid}", width="stretch",
                  on_click=go, args=(pid,))


def main():
    st.set_page_config(page_title=TITLE, page_icon="🌱", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    page = current_page()
    with st.sidebar:
        sidebar_nav(page)
        with st.container(key="side-status"):  # pinned to the bottom of the navigation (CSS)
            sidebar_status()
    st.title(f"{TITLE}: Position Value Model")
    st.caption(f"流程：{TAB_DATA} → {TAB_TRAIN} → {TAB_MATCH}。工作都在背景程序依序執行，關掉這個頁面或 UI 都不會中斷。"
               f"模擬、結果與回放請用 Dashboard（{DASHBOARD_URL}）。")
    started = st.session_state.pop("job-started", None)
    if started:
        st.toast(started)
    next(p for p in PAGES if p[0] == page)[3]()


main()
