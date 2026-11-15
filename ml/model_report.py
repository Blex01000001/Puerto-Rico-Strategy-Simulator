"""Summary of every model (official ml/models and local ml/local/models) as a Markdown table.

    python3 ml/model_report.py            # all models
    python3 ml/model_report.py --players 4

Reads each <model>.meta.json (and the local match records of official models). Use it to fill in or check the model
list in docs/models.md: the win rates there must come from these records, never from memory.
Columns: vs the original MCTS at the same simulation count, at about equal time (the model gets fewer simulations),
and vs the hand-written table; each as win share ± 95% (games).
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import modelmeta  # noqa: E402


def classify(m):
    """'same' / 'time' (vs the original MCTS with equal / fewer simulations), 'hand', or None (vs another model)."""
    mcts = [o for o in m["others"] if o["strategy"] == "mcts"]
    if not mcts:
        return "hand"
    if any(o.get("valueModel") for o in mcts):
        return None
    base = mcts[0].get("simulations")
    return "same" if base == m.get("simulations") else "time"


def best(matches, kind):
    rows = [m for m in matches if classify(m) == kind]
    if not rows:
        return "—"
    m = max(rows, key=lambda r: r["winShare"])
    leaf = f"，leafRollout {m['leafRollout']}" if m.get("leafRollout") else ""
    return f"{m['winShare']:.1%} ± {m['winShareCi95']:.1%}（{m['simulations']} 次{leaf}，{m['games']} 局）"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--players", type=int, choices=[3, 4])
    a = ap.parse_args()
    paths = []
    for folder in (modelmeta.OFFICIAL_MODELS, modelmeta.local_models_dir()):
        paths += [p for p in sorted(glob.glob(os.path.join(folder, "*")))
                  if p.endswith((".txt", ".json")) and not p.endswith((".meta.json", ".check.txt"))]
    print("| 模型 | 位置 | 人數 | 種類 | 資料列數 | 自我對戰資料來自 | 對原版（同模擬次數） | 對原版（約同時間） | 對手寫桌 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for p in paths:
        try:
            meta = modelmeta.read(p)
        except (OSError, ValueError):
            print(f"| {os.path.basename(p)} | {'正式' if modelmeta.is_official(p) else '本機'} | ? | ? | ? | ? | 沒有 .meta.json | | |")
            continue
        if a.players and meta["players"] != a.players:
            continue
        sources = sorted({os.path.basename(v) for d in meta["data"] for v in d.get("valueModels", [])})
        rows = sum(d["rows"] for d in meta["data"])
        print(f"| {os.path.basename(p)} | {'正式' if modelmeta.is_official(p) else '本機'} | {meta['players']} | "
              f"{'LightGBM' if meta['kind'] == 'lightgbm' else 'MLP'} | {rows:,} | {'、'.join(sources) or '—'} | "
              f"{best(meta.get('matches', []), 'same')} | {best(meta.get('matches', []), 'time')} | {best(meta.get('matches', []), 'hand')} |")


if __name__ == "__main__":
    main()
