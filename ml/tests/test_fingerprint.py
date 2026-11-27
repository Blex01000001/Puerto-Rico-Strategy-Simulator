import copy
import os

import fingerprint as fp
import train_lgbm
import train_mlp

META = {
    "format": "pr-positions", "formatVersion": 1, "featureVersion": 1, "games": 20000, "rate": 0.01, "players": 4, "seed": 101,
    "seatOrder": "Random", "name": "4p-hand-a",
    "seats": [{"id": "x0", "strategy": "cheap-engine", "params": {}}, {"id": "x1", "strategy": "build-first", "params": {}},
              {"id": "x2", "strategy": "harbor-rush", "params": {}}, {"id": "x3", "strategy": "corn-to-premium", "params": {}}],
}


def dump_fp(**changes):
    meta = copy.deepcopy(META)
    meta.update(changes)
    return fp.fingerprint(fp.dump_recipe(meta))


def test_canonical_form_ignores_key_order_and_number_spelling():
    assert fp.digest({"a": 1, "b": [1.0, 2]}) == fp.digest({"b": [1, 2.0], "a": 1.0})
    assert fp.digest({"a": 1}) != fp.digest({"a": 2})
    assert fp.digest({"a": True}) != fp.digest({"a": 1})  # a flag is not the number 1


def test_dump_fingerprint_depends_on_what_decides_the_data():
    base = dump_fp()
    assert base == dump_fp(name="renamed", threads=3)  # names and thread counts do not count
    for change in ({"seed": 102}, {"games": 200000}, {"rate": 0.001}, {"seatOrder": "Balanced"}, {"players": 3},
                   {"rulesRevision": 2}, {"featureVersion": 2}, {"limits": {"maxRounds": 100}},
                   {"options": {"autoAdvanceForced": False}}):
        assert dump_fp(**change) != base, change
    assert dump_fp(seatOrder="random") == base  # the engine writes "Random", configs say "random"


def test_seat_ids_do_not_count_but_seat_order_does():
    base = dump_fp()
    seats = copy.deepcopy(META["seats"])
    for i, s in enumerate(seats):
        s["id"] = f"other-{i}"
    assert dump_fp(seats=seats) == base
    assert dump_fp(seats=list(reversed(seats))) != base
    seats[0]["params"] = {"x": 1}
    assert dump_fp(seats=seats) != base


def test_files_from_before_the_revision_field_count_as_revision_1():
    assert dump_fp() == dump_fp(rulesRevision=1)
    assert fp.dump_recipe(META)["limits"] == fp.DEFAULT_LIMITS  # defaults filled in for old dumps


def test_value_models_count_by_content_not_by_name(tmp_path):
    a, b, c = tmp_path / "a.txt", tmp_path / "b.txt", tmp_path / "c.txt"
    a.write_text("tree 1")
    b.write_text("tree 1")
    c.write_text("tree 2")

    def with_model(path):
        seats = copy.deepcopy(META["seats"])
        seats[0] = {"id": "m", "strategy": "mcts", "params": {"simulations": 100, "valueModel": str(path)}}
        return dump_fp(seats=seats)
    assert with_model(a) == with_model(b)  # same content, other name
    assert with_model(a) != with_model(c)
    assert with_model(tmp_path / "gone.txt") != with_model(a)  # a missing model never equals a present one
    assert fp.model_digest(str(tmp_path / "gone.txt")).startswith("missing:")


def test_model_recipe_ignores_data_order_threads_and_hidden_spelling():
    r1 = fp.model_recipe("mlp", 1, ["b", "a"], {"hidden": "256,128", "epochs": 12, "threads": 4, "backend": "numpy", "device": "cpu"})
    r2 = fp.model_recipe("mlp", 1, ["a", "b"], {"hidden": [256, 128], "epochs": 12, "threads": 8, "backend": "numpy", "device": "cpu"})
    assert fp.fingerprint(r1) == fp.fingerprint(r2)
    r3 = fp.model_recipe("mlp", 1, ["a", "b"], {"hidden": "256,64", "epochs": 12, "backend": "numpy", "device": "cpu"})
    assert fp.fingerprint(r3) != fp.fingerprint(r1)


def test_every_training_option_is_hashed_or_explicitly_ignored():
    # a new option added to train_*.DEFAULTS must be listed in fingerprint.py, otherwise two different models could share a fingerprint
    assert set(train_lgbm.DEFAULTS) <= set(fp.LGBM_OPTIONS) | set(fp.IGNORED_OPTIONS)
    assert set(train_mlp.DEFAULTS) <= set(fp.MLP_OPTIONS) | set(fp.IGNORED_OPTIONS)


def test_describe_lists_the_differences_in_words():
    old = fp.dump_recipe(META)
    new = fp.dump_recipe({**META, "games": 200000, "rate": 0.001})
    assert fp.describe(old, new) == ["局數：20,000 → 200,000", "抽樣率：0.01 → 0.001"]
    seats = copy.deepcopy(META["seats"])
    seats[1]["params"] = {"simulations": 300}
    assert "座位 2 的模擬次數：（無） → 300" in fp.describe(old, fp.dump_recipe({**META, "seats": seats}))
    m_old = fp.model_recipe("lightgbm", 1, ["aaaaaaaa11", "bbbbbbbb22"], {"rounds": 400})
    m_new = fp.model_recipe("lightgbm", 1, ["aaaaaaaa11", "cccccccc33"], {"rounds": 500})
    text = fp.describe(m_old, m_new, names={"cccccccc33": "4p-hand-a-200k"})
    assert "訓練資料：新增 4p-hand-a-200k；移除 bbbbbbbb" in text and "參數 rounds：400 → 500" in text


def test_rules_revision_is_read_from_the_engine_source():
    src = open(os.path.join(fp.ROOT, "Engine", "Game", "EngineInfo.cs"), encoding="utf-8").read()
    assert f"RulesRevision = {fp.current_rules_revision()};" in src


def test_version_list_matches_the_numbers_in_the_engine_source():
    tracks, error = fp.load_versions()
    assert error is None
    latest = {k: t["entries"][0]["version"] for k, t in tracks.items()}
    assert latest["rules"] == str(fp.current_rules_revision())
    assert latest["engine"] == fp.current_engine_version()
    assert latest["features"] == str(fp.current_feature_version())
    assert latest["format"] == str(fp.current_format_version())
    assert fp.rules_name(2) == "base-v2"
    assert "規則版本：base-v1 → base-v2" in fp.describe({"rulesRevision": 1}, {"rulesRevision": 2})


def test_seats_are_resolved_like_the_engine_does():
    # ml/strategy-params.json is written from the engine (and checked by a C# test): these mirror StrategyRegistry.Resolve
    hr = fp.resolve_seat({"strategy": "harbor-rush"}, 4)
    assert hr["revisions"] == {"harbor-rush": 1} and "buildThreshold" in hr["params"] and "tieTile" in hr["params"]
    assert fp.resolve_seat({"strategy": "harbor-rush", "params": {"buildThreshold": 9}}, 4)["params"]["buildThreshold"] == 9
    rb = fp.resolve_seat({"strategy": "rule-based", "params": {"profile": "build-first"}}, 3)
    assert rb["revisions"] == {"build-first": 1} and rb["params"]["profile"] == "build-first"
    mcts = fp.resolve_seat({"strategy": "mcts", "params": {"rolloutStrategy": "guided-random"}}, 4)
    assert mcts["revisions"] == {"mcts": 1, "guided-random": 1} and mcts["params"]["simulations"] == 200


def test_mcts_leaf_rollout_default_matches_the_engine():
    import re
    src = open(os.path.join(os.path.dirname(fp.__file__), "..", "Engine", "Strategies", "Mcts", "MctsStrategy.cs"), encoding="utf-8").read()
    assert int(re.search(r"DefaultLeafRollout\s*=\s*(\d+)", src).group(1)) == fp.DEFAULT_LEAF_ROLLOUT
    leaf = lambda seat, players, **kw: fp.resolve_seat(seat, players, **kw)["params"]["leafRollout"]  # noqa: E731
    model = {"strategy": "mcts", "params": {"valueModel": "ml/models/4p-v2.txt"}}
    assert leaf(model, 4) == 40                                                  # a value model on 4 players
    assert leaf({"strategy": "mcts", "params": {}}, 4) == 0                       # no model
    assert leaf(model, 3) == 0                                                   # 3 players: not measured
    assert leaf({"strategy": "mcts", "params": {"valueModel": "m.txt", "leafRollout": 0}}, 4) == 0  # explicit wins
    assert leaf(model, 4, legacy=True) == 0                                      # files from before the engine recorded resolvedSeats


def test_old_files_are_hashed_with_the_frozen_defaults():
    # a dump from before the engine recorded resolvedSeats hashes like one that recorded exactly the legacy defaults
    resolved = [fp.resolve_seat(s, META["players"], legacy=True) for s in META["seats"]]
    assert dump_fp() == dump_fp(resolvedSeats=resolved)
    changed = copy.deepcopy(resolved)
    changed[0]["params"]["buildThreshold"] = 99  # a default that changed later is a different recipe
    assert dump_fp(resolvedSeats=changed) != dump_fp()
    newer = copy.deepcopy(resolved)
    newer[1]["revisions"] = {"build-first": 2}
    assert dump_fp(resolvedSeats=newer) != dump_fp()
    assert "座位 2 的策略版本 build-first：v1 → v2" in fp.describe(fp.dump_recipe(META), fp.dump_recipe({**META, "resolvedSeats": newer}))


def test_stale_notes_name_what_is_older_than_this_checkout(monkeypatch):
    now = fp.current_rules_revision()
    recipe = fp.dump_recipe({**META, "rulesRevision": now})  # data made with this checkout's rules
    assert fp.stale_notes(recipe) == []
    monkeypatch.setattr(fp, "current_rules_revision", lambda: now + 1)
    monkeypatch.setattr(fp, "current_strategy_revision", lambda name: 3 if name == "harbor-rush" else 1)
    notes = fp.stale_notes(recipe)
    assert f"規則 base-v{now} → base-v{now + 1}" in notes and "harbor-rush-v1 → v3" in notes


def test_recipe_reserves_ruleset_and_variant():
    r = fp.dump_recipe(META)
    assert r["ruleset"] == "base" and r["variant"] == "" and r["variantOptions"] == {} and r["hashFormat"] == fp.HASH_FORMAT


def test_planned_dump_recipe_follows_the_feature_version_asked_for():
    cfg = {"players": 4, "games": 100, "seed": 1, "seatOrder": "random", "seats": [{"id": "a", "strategy": "random"}] * 4}
    newest = fp.planned_dump_recipe(cfg, 0.01)
    assert newest["featureVersion"] == fp.current_feature_version() >= 2
    assert fp.planned_dump_recipe(cfg, 0.01, fp.current_feature_version()) == newest
    older = fp.planned_dump_recipe(cfg, 0.01, 1)
    assert older["featureVersion"] == 1 and fp.fingerprint(older) != fp.fingerprint(newest)
    assert fp.feature_versions() == list(range(1, fp.current_feature_version() + 1))


def test_engine_info_agrees_with_the_strategy_table():
    """ml/engine-info.json and ml/strategy-params.json are both written from the engine: the same strategies."""
    info = fp.engine_info()
    assert set(info["strategies"]) - {"rule-based"} == set(fp.strategy_table())
    assert set(info["handWritten"]) < set(info["strategies"])
    assert info["seatOrders"][0] == "random" and info["mctsParamOrder"][0] == "valueModel"
