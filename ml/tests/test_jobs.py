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
    jobs.cancel(job_id)
    job = jobs.wait(job_id, timeout=30)
    assert job["state"] == "cancelled"
    assert not os.path.exists(out)


def test_failure_is_reported(results):
    job_id = jobs.start("train_lgbm", "bad", {"data": [str(results / "missing.bin")], "out": str(results / "m.txt")})
    job = jobs.wait(job_id, timeout=60)
    assert job["state"] == "failed"
    assert "metadata" in job["error"]


def test_queue_runs_in_order_and_continues_after_cancel_and_failure(results, dump):
    big = dump("big.bin", games=400, per_game=10)
    small = dump("small.bin", games=40)
    long_id = jobs.start("train_mlp", "long", {"data": [big], "out": str(results / "long.json"),
                                               "options": {"hidden": "64", "epochs": 500, "batch": 16, "patience": 500}})
    bad_id = jobs.start("train_lgbm", "bad", {"data": [str(results / "missing.bin")], "out": str(results / "bad.txt")})
    ok_id = jobs.start("train_lgbm", "ok", {"data": [small], "out": str(results / "ok.txt"),
                                            "options": {"rounds": 5, "leaves": 4, "min_leaf": 5, "threads": 1}})
    assert jobs.read_job(bad_id)["state"] == "waiting" and jobs.read_job(ok_id)["state"] == "waiting"
    assert [jobs.queue_position(i) for i in (long_id, bad_id, ok_id)] == [None, 1, 2]
    deadline = time.time() + 60
    while not any(e["stage"] == "epoch" for e in jobs.events(long_id)):
        assert time.time() < deadline, jobs.log_tail(long_id)
        time.sleep(0.2)
    jobs.cancel(long_id)                        # cancelled ...
    assert jobs.wait(long_id, 60)["state"] == "cancelled"
    assert jobs.wait(bad_id, 60)["state"] == "failed"   # ... the next one still runs, and fails ...
    ok = jobs.wait(ok_id, 120)                  # ... and the one after it still runs
    assert ok["state"] == "done", jobs.log_tail(ok_id)
    started = [jobs.read_job(i)["started"] for i in (long_id, bad_id, ok_id)]
    assert started == sorted(started)
    assert jobs.active_job() is None and jobs.waiting_jobs() == []


def test_cancelling_a_waiting_job_removes_it_from_the_queue(results, dump):
    big = dump("big.bin", games=400, per_game=10)
    long_id = jobs.start("train_mlp", "long", {"data": [big], "out": str(results / "long.json"),
                                               "options": {"hidden": "64", "epochs": 500, "batch": 16, "patience": 500}})
    later = jobs.start("train_lgbm", "later", {"data": [big], "out": str(results / "later.txt")})
    jobs.cancel(later)
    job = jobs.read_job(later)
    assert job["state"] == "cancelled" and "started" not in job
    jobs.cancel(long_id)
    assert jobs.wait(long_id, 60)["state"] == "cancelled"
    assert "started" not in jobs.read_job(later)  # never ran
    assert not os.path.exists(results / "later.txt")


def test_queue_resumes_after_a_job_died_without_handing_over(results, dump):
    import json as _json
    d = os.path.join(jobs.jobs_dir(), "dead")
    os.makedirs(d)
    with open(os.path.join(d, "job.json"), "w", encoding="utf-8") as f:
        _json.dump({"id": "dead", "kind": "train_lgbm", "title": "dead", "status": "running",
                    "createdEpoch": time.time() - 999, "heartbeatEpoch": time.time() - 999}, f)
    small = dump("small.bin", games=40)
    job_id = jobs.start("train_lgbm", "next", {"data": [small], "out": str(results / "n.txt"),
                                               "options": {"rounds": 5, "leaves": 4, "min_leaf": 5, "threads": 1}})
    assert jobs.wait(job_id, 120)["state"] == "done"  # the dead job (interrupted) does not block the queue


def test_stale_heartbeat_shows_as_interrupted(results):
    d = os.path.join(jobs.jobs_dir(), "old")
    os.makedirs(d)
    with open(os.path.join(d, "job.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "old", "kind": "train_lgbm", "title": "t", "status": "running",
                   "createdEpoch": time.time() - 999, "heartbeatEpoch": time.time() - 999}, f)
    assert jobs.read_job("old")["state"] == "interrupted"
    assert jobs.active_job() is None  # an interrupted job does not block new ones


def test_job_file_write_survives_a_reader_holding_it_on_windows(tmp_path, monkeypatch):
    # Windows: replacing job.json fails with PermissionError while the UI has it open; the write retries instead of
    # killing the heartbeat (which made a running dump show as interrupted after about 10 minutes)
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) <= 3:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        real(src, dst)

    monkeypatch.setattr(jobs.os, "replace", flaky)
    path = str(tmp_path / "job.json")
    jobs._write_json(path, {"status": "running"})
    assert len(calls) == 4
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"status": "running"}


def test_heartbeat_keeps_running_after_a_failed_write(monkeypatch):
    import threading
    import job_runner

    class FakeJob:
        cancelling, child, beats = False, None, 0

        def cancel_requested(self):
            return False

        def update(self):
            self.beats += 1
            if self.beats == 1:
                raise PermissionError(13, "in use")

    monkeypatch.setattr(jobs, "HEARTBEAT_SECONDS", 0.01)
    job, stop = FakeJob(), threading.Event()
    t = threading.Thread(target=job_runner.heartbeat, args=(job, stop), daemon=True)
    t.start()
    deadline = time.time() + 5
    while job.beats < 3 and time.time() < deadline:
        time.sleep(0.01)
    stop.set()
    t.join(2)
    assert job.beats >= 3  # the first write failed, the thread kept beating


def test_unknown_kind_is_refused(results):
    with pytest.raises(ValueError):
        jobs.start("rm -rf", "x", {})


def test_job_output_never_fails_on_encoding(tmp_path):
    # Windows (cp950) once crashed printing the Runner's "±" / a replacement character: the job runner switches its
    # output to UTF-8 even when the default encoding cannot encode them (here: ascii)
    import subprocess
    import sys
    code = "import sys; sys.path.insert(0, %r); import job_runner; job_runner.utf8_output(); print('± \\ufffd 勝率')" % jobs.ML_DIR
    out = tmp_path / "log.txt"
    with open(out, "wb") as f:
        r = subprocess.run([sys.executable, "-c", code], stdout=f, stderr=subprocess.STDOUT,
                           env={**os.environ, "PYTHONIOENCODING": "ascii"})
    assert r.returncode == 0, out.read_text(errors="replace")
    assert "± \ufffd 勝率" in out.read_text(encoding="utf-8")


def test_runner_output_decoding_falls_back_to_the_locale():
    import job_runner
    assert job_runner.decode("勝率 ±".encode("utf-8")) == "勝率 ±"
    assert job_runner.decode(b"\xff\xfe abc").endswith("abc")  # not UTF-8: decoded with the locale, never raises
