"""Runner-based jobs (dump, match) end to end: needs the .NET SDK; publishes the Runner once into a temp folder."""
import json
import os
import shutil
import time

import pytest

import jobs
import modelmeta
import positions

ROOT = jobs.ROOT
pytestmark = pytest.mark.skipif(shutil.which("dotnet") is None, reason="needs the .NET SDK")


@pytest.fixture(scope="module")
def runner_dir(tmp_path_factory):
    return str(tmp_path_factory.mktemp("runner"))  # empty: the first job publishes into it


@pytest.fixture
def env(tmp_path, monkeypatch, runner_dir):
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("PR_RUNNER_DIR", runner_dir)
    return tmp_path


def write_config(path, seats, players=4, games=24, seed=5, order="balanced"):
    cfg = {"schemaVersion": 1, "name": os.path.basename(path)[:-5], "players": players, "games": games, "seed": seed,
           "seatOrder": order, "seats": seats, "output": {"perGameRecords": False}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return path


def test_dump_job_publishes_the_runner_and_writes_a_readable_dump(env, runner_dir):
    cfg = write_config(str(env / "d.json"), [{"id": f"r{i}", "strategy": "random", "params": {}} for i in range(4)], games=40)
    out = str(env / "results" / "ml" / "d.bin")
    job_id = jobs.start("dump", "dump", {"config": cfg, "out": out, "rate": 0.05})
    job = jobs.wait(job_id, timeout=600)
    assert job["state"] == "done", jobs.log_tail(job_id)
    assert os.path.exists(os.path.join(runner_dir, "Runner.dll"))
    meta = positions.read_meta(out)
    assert meta["games"] == 40 and meta["status"] == "completed"
    assert job["result"]["rows"] == meta["rows"]
    games = [e for e in jobs.events(job_id) if e["stage"] == "games"]
    assert games and games[-1]["done"] == 40


def test_cancelled_dump_keeps_the_finished_games(env):
    cfg = write_config(str(env / "d.json"), [{"id": f"r{i}", "strategy": "random", "params": {}} for i in range(4)], games=3_000_000)
    out = str(env / "results" / "ml" / "big.bin")
    job_id = jobs.start("dump", "big", {"config": cfg, "out": out, "rate": 0.001})
    deadline = time.time() + 300
    while not any(e["stage"] == "games" for e in jobs.events(job_id)):
        assert time.time() < deadline, jobs.log_tail(job_id)
        time.sleep(0.2)
    jobs.cancel(job_id)
    job = jobs.wait(job_id, timeout=120)
    assert job["state"] == "cancelled", jobs.log_tail(job_id)
    if os.name != "nt":  # Windows ends the Runner instead of Ctrl+C: nothing to keep
        meta = positions.read_meta(out)
        assert meta["status"] == "cancelled" and 0 < meta["games"] < 3_000_000


def test_match_job_records_the_win_rate_in_the_model(env):
    model = str(env / "tiny.txt")
    shutil.copy(os.path.join(ROOT, "Tests", "Data", "tiny-lgbm.txt"), model)
    fake = [{"path": "x.bin", "rows": 1, "games": 1, "status": "completed", "rate": 1, "seed": 1, "players": 4,
             "featureVersion": 1, "featureCount": 430, "seats": []}]
    modelmeta.write(model, "lightgbm", fake, {}, {}, {}, [], {})
    seats = [{"id": "A", "strategy": "mcts", "params": {"simulations": 5, "valueModel": model}},
             {"id": "B", "strategy": "mcts", "params": {"simulations": 5}},
             {"id": "cheap-engine", "strategy": "cheap-engine", "params": {}},
             {"id": "build-first", "strategy": "build-first", "params": {}}]
    cfg = write_config(str(env / "m.json"), seats, games=24)
    out = str(env / "results" / "ml" / "m.json")
    job_id = jobs.start("match", "match", {"config": cfg, "out": out, "model": model})
    job = jobs.wait(job_id, timeout=600)
    assert job["state"] == "done", jobs.log_tail(job_id)
    matches = modelmeta.read(model)["matches"]
    assert len(matches) == 1 and matches[0]["games"] == 24 and matches[0]["simulations"] == 5
    assert job["result"]["match"]["winShare"] == matches[0]["winShare"]
