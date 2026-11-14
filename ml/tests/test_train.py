import json
import os

import numpy as np

import modelmeta
import train_lgbm
import train_mlp


def test_lightgbm_writes_model_meta_and_check_rows(dump, tmp_path):
    data = [dump("a.bin", games=60), dump("b.bin", games=40, seed=2)]
    out = str(tmp_path / "m.txt")
    events = []
    meta = train_lgbm.train(data, out, progress=events.append, log=lambda *_: None,
                            rounds=20, leaves=4, min_leaf=5, threads=1)
    assert os.path.exists(out) and os.path.exists(out + ".check.txt")
    assert modelmeta.read(out) == meta
    assert meta["kind"] == "lightgbm"
    assert meta["players"] == 4 and meta["featureVersion"] == 1
    assert [d["rows"] for d in meta["data"]] == [1200, 800]
    assert meta["data"][0]["valueModels"] == ["ml/models/x.txt"]
    assert meta["params"]["num_leaves"] == 4
    assert len(meta["training"]["validLossCurve"]) == meta["training"]["iterations"]
    assert meta["validation"]["r2"] > 0.3  # the synthetic label is learnable
    assert meta["topFeatures"][0]["name"] in ("p0_score", "p1_score")
    assert events[0]["stage"] == "loaded" and events[-1]["stage"] == "done"
    assert any(e["stage"] == "iteration" for e in events)
    assert meta["matches"] == []


def test_lightgbm_is_deterministic(dump, tmp_path):
    data = [dump(games=40)]
    a, b = str(tmp_path / "a.txt"), str(tmp_path / "b.txt")
    for out in (a, b):
        train_lgbm.train(data, out, log=lambda *_: None, rounds=10, leaves=4, min_leaf=5, threads=1)
    trees = [open(p, encoding="utf-8").read().split("end of trees")[0] for p in (a, b)]
    assert trees[0] == trees[1]


def test_mlp_writes_engine_format_and_meta(dump, tmp_path):
    out = str(tmp_path / "m.json")
    events = []
    meta = train_mlp.train([dump(games=60)], out, progress=events.append, log=lambda *_: None,
                           hidden="8", epochs=3, batch=64, patience=1)
    with open(out, encoding="utf-8") as f:
        model = json.load(f)
    assert model["format"] == "mlp" and model["features"][1] == "round"
    assert [len(layer["bias"]) for layer in model["layers"]] == [8, 1]
    assert len(model["layers"][0]["weights"][0]) == 6  # [out][in]
    assert meta["kind"] == "mlp" and meta["params"]["hidden"] == [8]
    assert 1 <= meta["training"]["bestEpoch"] <= meta["training"]["epochsRun"] <= 3
    assert sum(e["stage"] == "epoch" for e in events) == meta["training"]["epochsRun"]
    check = np.loadtxt(out + ".check.txt")
    assert check.shape == (5, 7)


def test_match_results_are_appended_to_meta(dump, tmp_path):
    out = str(tmp_path / "m.txt")
    train_lgbm.train([dump(games=40)], out, log=lambda *_: None, rounds=5, leaves=4, min_leaf=5, threads=1)
    result = {
        "status": "completed",
        "config": {"name": "t", "seed": 7, "seatOrder": "Balanced", "seats": [
            {"id": "A", "strategy": "mcts", "params": {"simulations": 300, "valueModel": "ml/models/m.txt"}},
            {"id": "B", "strategy": "mcts", "params": {"simulations": 300}},
            {"id": "c", "strategy": "cheap-engine", "params": {}}]},
        "summary": [{"seatId": "A", "games": 100, "winShare": 0.6, "avgScore": 45.0},
                    {"seatId": "B", "games": 100, "winShare": 0.3, "avgScore": 40.0},
                    {"seatId": "c", "games": 100, "winShare": 0.1, "avgScore": 35.0}],
    }
    path = str(tmp_path / "r.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    modelmeta.add_match(out, path)
    entry = modelmeta.add_match(out, path)  # same result file again: replaced, not duplicated
    meta = modelmeta.read(out)
    assert len(meta["matches"]) == 1
    assert entry["winShare"] == 0.6 and entry["simulations"] == 300
    assert abs(entry["winShareCi95"] - 1.96 * (0.24 / 100) ** 0.5) < 1e-12
    assert [o["seatId"] for o in entry["others"]] == ["B", "c"]
