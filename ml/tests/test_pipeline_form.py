import pipeline_form as pf


def test_tokens_follow_the_rows_they_refer_to():
    assert pf.token_index("new:2") == 2 and pf.token_index("results/ml/a.bin") is None and pf.token_index("new:x") is None
    assert pf.shift_token("new:2", 1) == "new:1"          # a row before it went away
    assert pf.shift_token("new:0", 1) == "new:0"          # a row after it: unchanged
    assert pf.shift_token("new:1", 1) is None             # the row itself: the reference is dropped
    assert pf.shift_token("4p-v2.txt", 0) == "4p-v2.txt"   # an existing file or model is never touched
    assert pf.shift_tokens(["new:0", "new:1", "new:2", "x.bin"], 1) == ["new:0", "new:1", "x.bin"]
    assert pf.shift_tokens(["new:0", "x.bin"], None) == ["x.bin"]  # all rows removed


def test_a_template_of_the_first_pipeline_page_becomes_one_row_of_each():
    old = {"pl-players": 4, "pl-d-on": True, "pl-d-mode": "config", "pl-d-config": "ml/data-configs/4p-hand-a.json", "pl-d-name": "d1",
           "pl-d-games": 20000, "pl-d-games-for": "tok", "pl-t-on": True, "pl-t-kind": "train_lgbm", "pl-t-name": "m1",
           "pl-t-existing": ["results/ml/x.bin"], "pl-t-opt-train_lgbm-rounds": 99, "pl-m-n": 2, "pl-m0-table": "hand", "pl-m1-table": "default",
           "pl-m-sims": 300}
    new = pf.migrate_settings(old)
    assert new["pl-d-n"] == 1 and new["pl-t-n"] == 1 and new["pl-m-n"] == 2
    assert new["pl-d0-name"] == "d1" and new["pl-d0-games"] == 20000 and new["pl-d0-games-for"] == "tok"
    assert new["pl-t0-name"] == "m1" and new["pl-t0-opt-train_lgbm-rounds"] == 99
    assert new["pl-t0-data"] == ["new:0", "results/ml/x.bin"] and new["pl-t0-data-for"] == "init"
    assert new["pl-m0-model"] == "new:0" and new["pl-m1-model"] == "new:0"      # both matches play the model of the pipeline
    assert new["pl-m0-table"] == "hand" and new["pl-m-sims"] == 300 and new["pl-players"] == 4
    assert not any(k in new for k in ("pl-d-on", "pl-t-on", "pl-t0-existing", "pl-d-mode"))


def test_old_template_with_steps_switched_off_and_an_existing_model():
    old = {"pl-d-on": False, "pl-t-on": False, "pl-m-model": "4p-v2.txt", "pl-m-n": 1, "pl-m0-seed": 5}
    new = pf.migrate_settings(old)
    assert new["pl-d-n"] == 0 and new["pl-t-n"] == 0 and new["pl-m0-model"] == "4p-v2.txt" and new["pl-m0-seed"] == 5
    assert "pl-t0-data" not in new


def test_a_template_of_the_new_form_is_not_changed():
    new = {"pl-d-n": 2, "pl-t-n": 1, "pl-d0-name": "a", "pl-d1-name": "b", "pl-t0-data": ["new:0", "new:1"]}
    assert pf.migrate_settings(new) == new
    assert pf.migrate_settings({"pl-players": 4}) == {"pl-players": 4}
