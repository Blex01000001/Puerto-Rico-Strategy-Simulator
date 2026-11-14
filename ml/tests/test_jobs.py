import json
import os
import time

import pytest

import jobs


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setenv("PR_RESULTS_DIR", str(tmp_path / "results"))  # inherited by the job process
    return tmp_path


def test_training_job_runs_in_its_own_process(results, dump):
    data = dump("a.bin", games=60)
    out = str(results / "m.txt")
    job_id = jobs.start("train_lgbm", "tiny", {"data": [data], "out": out,
                                               "options": {"rounds": 10, "leaves": 4, "min_leaf": 5, "threads": 1}})
    job = jobs.wait(job_id, timeout=120)
    assert job["state"] == "done", jobs.log_tail(job_id)
    assert os.path.exists(out) and os.path.exists(out + ".meta.json")
    assert job["result"]["validation"]["r2"] > 0
    stages = [e["stage"] for e in jobs.events(job_id)]
    assert stages[0] == "loaded" and stages[-1] == "done" and "iteration" in stages
    assert "trained" in jobs.log_tail(job_id)
    assert jobs.list_jobs()[0]["id"] == job_id
    assert jobs.active_job() is None


def test_cancel_stops_the_job_without_writing_a_model(results, dump):
    data = dump("a.bin", games=400, per_game=10)
    out = str(results / "m.json")
    job_id = jobs.start("train_mlp", "long", {"data": [data], "out": out,
                                              "options": {"hidden": "64", "epochs": 500, "batch": 16, "patience": 500}})
    deadline = time.time() + 60
    while not any(e["stage"] == "epoch" for e in jobs.events(job_id)):
        assert time.time() < deadline, jobs.log_tail(job_id)
        time.sleep(0.2)
    with pytest.raises(RuntimeError, match="another job"):
        jobs.start("train_lgbm", "second", {"data": [data], "out": str(results / "x.txt")})  # one job at a time
    jobs.cancel(job_id)
    job = jobs.wait(job_id, timeout=30)
    assert job["state"] == "cancelled"
    assert not os.path.exists(out)


def test_failure_is_reported(results):
    job_id = jobs.start("train_lgbm", "bad", {"data": [str(results / "missing.bin")], "out": str(results / "m.txt")})
    job = jobs.wait(job_id, timeout=60)
    assert job["state"] == "failed"
    assert "metadata" in job["error"]


def test_stale_heartbeat_shows_as_interrupted(results):
    d = os.path.join(jobs.jobs_dir(), "old")
    os.makedirs(d)
    with open(os.path.join(d, "job.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "old", "kind": "train_lgbm", "title": "t", "status": "running",
                   "createdEpoch": time.time() - 999, "heartbeatEpoch": time.time() - 999}, f)
    assert jobs.read_job("old")["state"] == "interrupted"
    assert jobs.active_job() is None  # an interrupted job does not block new ones


def test_unknown_kind_is_refused(results):
    with pytest.raises(ValueError):
        jobs.start("rm -rf", "x", {})
