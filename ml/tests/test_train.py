import json
import os

import numpy as np
import pytest

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
    # recipe fingerprint: the model's own and one per data file; the same options and data give the same fingerprint
    assert len(meta["fingerprint"]) == 64 and meta["rulesRevision"] >= 1
    assert len({d["fingerprint"] for d in meta["data"]}) == 2 and meta["recipe"]["data"] == sorted(d["fingerprint"] for d in meta["data"])
    again = train_lgbm.train(data, str(tmp_path / "again.txt"), log=lambda *_: None, rounds=20, leaves=4, min_leaf=5, threads=2)
    assert again["fingerprint"] == meta["fingerprint"]  # thread count is not part of the recipe
    other = train_lgbm.train(data, str(tmp_path / "other.txt"), log=lambda *_: None, rounds=21, leaves=4, min_leaf=5, threads=1)
    assert other["fingerprint"] != meta["fingerprint"]


def test_lightgbm_trees_do_not_depend_on_the_thread_count(dump, tmp_path):
    # the fingerprint leaves the thread count out: that is only right if the trained trees really do not depend on it
    data = [dump(games=60)]
    a, b = str(tmp_path / "t1.txt"), str(tmp_path / "t3.txt")
    train_lgbm.train(data, a, log=lambda *_: None, rounds=15, leaves=8, min_leaf=5, threads=1)
    train_lgbm.train(data, b, log=lambda *_: None, rounds=15, leaves=8, min_leaf=5, threads=3)
    trees = [open(p, encoding="utf-8").read().split("end of trees")[0] for p in (a, b)]
    assert trees[0] == trees[1]


def test_lightgbm_is_deterministic(dump, tmp_path):
    data = [dump(games=40)]
    a, b = str(tmp_path / "a.txt"), str(tmp_path / "b.txt")
    for out in (a, b):
        train_lgbm.train(data, out, log=lambda *_: None, rounds=10, leaves=4, min_leaf=5, threads=1)
    trees = [open(p, encoding="utf-8").read().split("end of trees")[0] for p in (a, b)]
    assert trees[0] == trees[1]


@pytest.mark.parametrize("backend", ["numpy", "torch"])
def test_mlp_writes_engine_format_and_meta(dump, tmp_path, backend):
    if backend == "torch" and not train_mlp.torch_available():
        pytest.skip("PyTorch not installed")
    out = str(tmp_path / "m.json")
    events = []
    meta = train_mlp.train([dump(games=60)], out, progress=events.append, log=lambda *_: None,
                           hidden="8", epochs=3, batch=64, patience=1, backend=backend, device="cpu")
    with open(out, encoding="utf-8") as f:
        model = json.load(f)
    assert model["format"] == "mlp" and model["features"][1] == "round"
    assert [len(layer["bias"]) for layer in model["layers"]] == [8, 1]
    assert len(model["layers"][0]["weights"][0]) == 6  # [out][in]
    assert meta["kind"] == "mlp" and meta["params"]["hidden"] == [8] and meta["params"]["backend"] == backend
    assert 1 <= meta["training"]["bestEpoch"] <= meta["training"]["epochsRun"] <= 3
    assert sum(e["stage"] == "epoch" for e in events) == meta["training"]["epochsRun"]
    # the exported JSON alone (what the engine reads) reproduces the check rows
    check = np.loadtxt(out + ".check.txt")
    assert check.shape == (5, 7)
    x = (check[:, 1:] - np.array(model["mean"])) / np.array(model["scale"])
    for i, layer in enumerate(model["layers"]):
        x = x @ np.array(layer["weights"]).T + np.array(layer["bias"])
        if i < len(model["layers"]) - 1:
            x = np.maximum(x, 0)
    assert np.allclose(1 / (1 + np.exp(-x[:, 0])), check[:, 0], atol=1e-5)


def test_mlp_torch_backend_refused_when_missing(dump, tmp_path, monkeypatch):
    monkeypatch.setattr(train_mlp, "torch_available", lambda: False)
    with pytest.raises(RuntimeError, match="PyTorch"):
        train_mlp.train([dump()], str(tmp_path / "m.json"), log=lambda *_: None, backend="torch")
    meta = train_mlp.train([dump("b.bin")], str(tmp_path / "n.json"), log=lambda *_: None, hidden="4", epochs=1, backend="auto")
    assert meta["params"]["backend"] == "numpy"


def test_match_results_are_appended_to_meta(dump, tmp_path):
    out = str(tmp_path / "m.txt")
    train_lgbm.train([dump(games=40)], out, log=lambda *_: None, rounds=5, leaves=4, min_leaf=5, threads=1)
    result = {
        "status": "completed",
        "config": {"name": "t", "players": 4, "games": 240, "seed": 7, "seatOrder": "Balanced", "seats": [
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


def test_official_models_keep_local_matches_beside_them(dump, tmp_path, monkeypatch):
    official = tmp_path / "ml" / "models"
    local = tmp_path / "ml" / "local"
    official.mkdir(parents=True)
    monkeypatch.setattr(modelmeta, "OFFICIAL_MODELS", str(official))
    monkeypatch.setattr(modelmeta, "LOCAL_DIR", str(local))
    out = str(official / "m.txt")
    train_lgbm.train([dump(games=40)], out, log=lambda *_: None, rounds=5, leaves=4, min_leaf=5, threads=1)
    tracked = open(out + ".meta.json", encoding="utf-8").read()
    result = {"status": "completed", "config": {"name": "t", "players": 4, "games": 240, "seed": 7, "seatOrder": "Balanced", "seats": [
        {"id": "A", "strategy": "mcts", "params": {"simulations": 300, "valueModel": "ml/models/m.txt"}},
        {"id": "B", "strategy": "mcts", "params": {"simulations": 300}}]},
        "summary": [{"seatId": "A", "games": 24, "winShare": 0.6, "avgScore": 45.0},
                    {"seatId": "B", "games": 24, "winShare": 0.4, "avgScore": 40.0}]}
    path = str(tmp_path / "r.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    modelmeta.add_match(out, path)
    assert open(out + ".meta.json", encoding="utf-8").read() == tracked  # the tracked file is untouched
    meta = modelmeta.read(out)
    assert len(meta["matches"]) == 1 and meta["matches"][0]["local"] is True
    assert modelmeta.read(out, include_local=False)["matches"] == []
    # moving it to the local workspace carries the matches into its own metadata
    moved = modelmeta.move_model(out, modelmeta.local_models_dir())
    assert not os.path.exists(out) and os.path.exists(moved + ".check.txt")
    assert len(modelmeta.read(moved)["matches"]) == 1
    # and promoting it back: refused when the name is taken
    open(out, "w").close()
    import pytest as _pt
    with _pt.raises(ValueError):
        modelmeta.move_model(moved, str(official))


def test_training_creates_the_output_folder(dump, tmp_path):
    out = str(tmp_path / "local" / "models" / "m.txt")  # folder does not exist yet
    train_lgbm.train([dump(games=40)], out, log=lambda *_: None, rounds=3, leaves=4, min_leaf=5, threads=1)
    assert os.path.exists(out) and os.path.exists(out + ".meta.json")
    out2 = str(tmp_path / "other" / "m.json")
    train_mlp.train([dump("b.bin", games=40)], out2, log=lambda *_: None, hidden="4", epochs=1, backend="numpy")
    assert os.path.exists(out2)


def test_rename_moves_the_three_files_and_the_name_inside(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(modelmeta, "OFFICIAL_MODELS", str(tmp_path / "official"))
    monkeypatch.setattr(modelmeta, "local_models_dir", lambda: str(tmp_path / "local"))
    local = tmp_path / "local"
    local.mkdir()
    old = local / "4p-lgbm-1116-1530.txt"
    for suffix, text in (("", "tree"), (".meta.json", json.dumps({"model": old.name, "matches": [{"result": "r.json"}]})), (".check.txt", "1 2")):
        (local / (old.name + suffix)).write_text(text, encoding="utf-8")
    new = modelmeta.rename_model(str(old), "4p-v2-200k-big")
    assert new.endswith("4p-v2-200k-big.txt")
    assert sorted(p.name for p in local.iterdir()) == ["4p-v2-200k-big.txt", "4p-v2-200k-big.txt.check.txt", "4p-v2-200k-big.txt.meta.json"]
    meta = json.loads((local / "4p-v2-200k-big.txt.meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == "4p-v2-200k-big.txt" and meta["matches"] == [{"result": "r.json"}]  # match records follow
    assert modelmeta.rename_model(new, "x.txt").endswith("x.txt")  # the extension may be typed or not


def test_rename_updates_the_metadata_and_chosen_configs_that_name_the_model(tmp_path, monkeypatch):
    import json
    official, ws = tmp_path / "official", tmp_path / "ws"
    local, records, cfgs = ws / "models", ws / "match-records", ws / "matches"
    for d in (official, local, records, cfgs, ws / "data-configs"):
        d.mkdir(parents=True)
    monkeypatch.setattr(modelmeta, "OFFICIAL_MODELS", str(official))
    monkeypatch.setattr(modelmeta, "LOCAL_DIR", str(ws))
    monkeypatch.setattr(modelmeta, "local_models_dir", lambda: str(local))
    monkeypatch.setattr(modelmeta, "local_records_dir", lambda: str(records))
    (local / "old.txt").write_text("tree")
    (local / "old.txt.meta.json").write_text(json.dumps({"model": "old.txt", "matches": []}))
    other = {"model": "b.txt", "data": [{"valueModels": ["ml/local/models/old.txt", "ml/models/z.txt"]}],
             "matches": [{"others": [{"valueModel": "ml/local/models/old.txt"}, {"valueModel": None}, {"valueModel": "ml/models/z.txt"}]}]}
    (local / "b.txt").write_text("tree")
    (local / "b.txt.meta.json").write_text(json.dumps(other))
    (records / "c.txt.matches.json").write_text(json.dumps([{"others": [{"valueModel": "ml\\local\\models\\old.txt"}]}]))
    tracked = json.dumps({"model": "c.txt", "matches": [{"others": [{"valueModel": "ml/local/models/old.txt"}]}]})
    (official / "c.txt.meta.json").write_text(tracked)
    seat = {"strategy": "mcts", "params": {"valueModel": "ml/local/models/old.txt"}}
    for n in ("pick.json", "keep.json"):
        (cfgs / n).write_text(json.dumps({"seats": [seat, {"strategy": "random"}]}))
    refs = modelmeta.model_references(str(local / "old.txt"))
    assert refs["meta"] == [str(local / "b.txt.meta.json"), str(records / "c.txt.matches.json")]
    assert refs["official"] == [str(official / "c.txt.meta.json")]
    assert refs["configs"] == [str(cfgs / "keep.json"), str(cfgs / "pick.json")]
    with pytest.raises(ValueError):  # only configs in ml/local
        modelmeta.rename_model(str(local / "old.txt"), "new", configs=[str(official / "c.txt.meta.json")])
    modelmeta.rename_model(str(local / "old.txt"), "new", configs=[str(cfgs / "pick.json")])
    b = json.loads((local / "b.txt.meta.json").read_text())
    assert b["data"][0]["valueModels"] == ["ml/local/models/new.txt", "ml/models/z.txt"]
    assert [o["valueModel"] for o in b["matches"][0]["others"]] == ["ml/local/models/new.txt", None, "ml/models/z.txt"]
    assert json.loads((records / "c.txt.matches.json").read_text())[0]["others"][0]["valueModel"] == "ml\\local\\models\\new.txt"
    assert (official / "c.txt.meta.json").read_text() == tracked  # tracked by git: untouched
    assert json.loads((cfgs / "pick.json").read_text())["seats"][0]["params"]["valueModel"] == "ml/local/models/new.txt"
    assert json.loads((cfgs / "keep.json").read_text())["seats"][0]["params"]["valueModel"] == "ml/local/models/old.txt"


def test_rename_refuses_bad_names_taken_names_and_official_models(tmp_path, monkeypatch):
    official, local = tmp_path / "official", tmp_path / "local"
    official.mkdir()
    local.mkdir()
    monkeypatch.setattr(modelmeta, "OFFICIAL_MODELS", str(official))
    monkeypatch.setattr(modelmeta, "local_models_dir", lambda: str(local))
    (local / "a.txt").write_text("x")
    (local / "b.txt").write_text("x")
    (official / "c.txt").write_text("x")
    for bad in ("", "a b", "x/y", "a"):
        with pytest.raises(ValueError):
            modelmeta.rename_model(str(local / "a.txt"), bad)
    with pytest.raises(ValueError):
        modelmeta.rename_model(str(local / "a.txt"), "b")  # taken locally
    with pytest.raises(ValueError):
        modelmeta.rename_model(str(local / "a.txt"), "c")  # taken by an official model
    with pytest.raises(ValueError):
        modelmeta.rename_model(str(official / "c.txt"), "d")  # official models stay as git has them
