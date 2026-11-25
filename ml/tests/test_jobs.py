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


def _stale_job(job_id, **fields):
    d = os.path.join(jobs.jobs_dir(), job_id)
    os.makedirs(d)
    job = {"id": job_id, "kind": "dump", "title": job_id, "status": "running", "spec": {},
           "createdEpoch": time.time() - 999, "heartbeatEpoch": time.time() - 999, **fields}
    with open(os.path.join(d, "job.json"), "w", encoding="utf-8") as f:
        json.dump(job, f)


def _fake_runner():
    """A process that looks like a job runner (its command line names job_runner) and leads its own session."""
    import subprocess
    import sys
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "job_runner"], **kwargs)


def test_stale_heartbeat_with_a_live_process_is_lost_and_holds_the_queue(results):
    proc = _fake_runner()
    try:
        time.sleep(0.2)
        _stale_job("lost", pid=proc.pid, startedEpoch=time.time())
        assert jobs.read_job("lost")["state"] == "lost"
        assert jobs.active_job()["id"] == "lost"  # nothing else may start meanwhile
        waiting = jobs.start("dump", "next", {})
        assert jobs.read_job(waiting)["state"] == "waiting"
        # the user ends it: the process is killed, the job is cancelled and the queue moves on
        jobs.cancel("lost")
        proc.wait(timeout=10)
        assert jobs.read_job("lost")["state"] == "cancelled"
        assert jobs.read_job(waiting)["state"] != "waiting"
    finally:
        if proc.poll() is None:
            proc.kill()


def test_a_recycled_pid_does_not_count_as_alive(results):
    proc = _fake_runner()
    try:
        time.sleep(0.2)
        # the job started long before this process existed: its pid was reused by another process
        _stale_job("old", pid=proc.pid, startedEpoch=time.time() - 3600)
        assert jobs.read_job("old")["state"] == "interrupted"
        _stale_job("other", pid=os.getpid(), startedEpoch=time.time())  # pytest: not a job runner
        assert jobs.read_job("other")["state"] == "interrupted"
    finally:
        proc.kill()
        proc.wait()


def test_a_finished_process_is_interrupted(results):
    proc = _fake_runner()
    proc.kill()
    proc.wait()
    _stale_job("dead", pid=proc.pid, startedEpoch=time.time())
    assert jobs.read_job("dead")["state"] == "interrupted"


# ---------------------------------------------------------------- pipelines

def _train_step(results, data, name, stage="train", ok=True):
    spec = {"data": [data if ok else str(results / "missing.bin")], "out": str(results / f"{name}.txt"),
            "options": {"rounds": 5, "leaves": 4, "min_leaf": 5, "threads": 1}}
    return {"kind": "train_lgbm", "title": name, "spec": spec, "stage": stage}


def test_pipeline_jobs_run_in_the_given_order(results, dump):
    small = dump("small.bin", games=40)
    ids = jobs.start_pipeline("p", [_train_step(results, small, n) for n in ("a", "b", "c")])
    assert [jobs.read_job(i)["pipeline"]["index"] for i in ids] == [0, 1, 2]
    assert all(jobs.read_job(i)["pipeline"]["name"] == "p" and jobs.read_job(i)["pipeline"]["total"] == 3 for i in ids)
    done = [jobs.wait(i, 180) for i in ids]
    assert [j["state"] for j in done] == ["done"] * 3, jobs.log_tail(ids[0])
    started = [j["started"] for j in done]
    assert started == sorted(started)
    assert [j["id"] for j in jobs.pipeline_jobs(done[0]["pipeline"]["id"])] == ids


def test_a_failed_job_stops_the_rest_of_its_pipeline_but_not_other_jobs(results, dump):
    small = dump("small.bin", games=40)
    ids = jobs.start_pipeline("p", [_train_step(results, small, "first"), _train_step(results, small, "bad", ok=False),
                                    _train_step(results, small, "never1"), _train_step(results, small, "never2")])
    other = jobs.start("train_lgbm", "other", _train_step(results, small, "other")["spec"])  # queued after the pipeline, not part of it
    assert jobs.wait(ids[0], 180)["state"] == "done"
    assert jobs.wait(ids[1], 120)["state"] == "failed"
    jobs.start_next()  # the runner does this itself; the cancellation of the rest happens here
    for i in ids[2:]:
        j = jobs.wait(i, 60)
        assert j["state"] == "cancelled" and "started" not in j
        assert j["result"]["stoppedBy"] == ids[1] and j["result"]["stoppedByState"] == "failed"
    assert not os.path.exists(results / "never1.txt") and os.path.exists(results / "first.txt")  # what was written stays
    assert jobs.wait(other, 180)["state"] == "done"  # an unrelated job is not touched


def test_cancelling_a_waiting_pipeline_job_cancels_the_rest_of_its_pipeline(results, dump):
    big = dump("big.bin", games=400, per_game=10)
    small = dump("small.bin", games=40)
    long_id = jobs.start("train_mlp", "long", {"data": [big], "out": str(results / "long.json"),
                                               "options": {"hidden": "64", "epochs": 500, "batch": 16, "patience": 500}})
    ids = jobs.start_pipeline("p", [_train_step(results, small, n) for n in ("a", "b", "c")])
    other = jobs.start("train_lgbm", "other", _train_step(results, small, "other")["spec"])
    jobs.cancel(ids[1])
    states = [jobs.read_job(i)["state"] for i in ids]
    assert states == ["cancelled", "cancelled", "cancelled"]  # the first one had not started either: nothing of the pipeline runs
    assert jobs.read_job(other)["state"] == "waiting"
    jobs.cancel(long_id)
    assert jobs.wait(long_id, 60)["state"] == "cancelled"
    assert jobs.wait(other, 180)["state"] == "done"


def test_cancel_pipeline_stops_the_running_job_and_removes_the_waiting_ones(results, dump):
    big = dump("big.bin", games=400, per_game=10)
    small = dump("small.bin", games=40)
    long_step = {"kind": "train_mlp", "title": "long", "stage": "train",
                 "spec": {"data": [big], "out": str(results / "long.json"), "options": {"hidden": "64", "epochs": 500, "batch": 16, "patience": 500}}}
    ids = jobs.start_pipeline("p", [long_step, _train_step(results, small, "b"), _train_step(results, small, "c")])
    deadline = time.time() + 60
    while not any(e["stage"] == "epoch" for e in jobs.events(ids[0])):
        assert time.time() < deadline, jobs.log_tail(ids[0])
        time.sleep(0.2)
    pid = jobs.read_job(ids[0])["pipeline"]["id"]
    jobs.cancel_pipeline(pid)
    assert [jobs.read_job(i)["state"] for i in ids[1:]] == ["cancelled", "cancelled"]
    assert jobs.wait(ids[0], 60)["state"] == "cancelled"
    assert jobs.active_job() is None and jobs.waiting_jobs() == []
    assert not os.path.exists(results / "b.txt")


def test_an_interrupted_pipeline_job_stops_the_rest_too(results):
    pid = "pipe-x"
    d = os.path.join(jobs.jobs_dir(), "dead")
    os.makedirs(d)
    with open(os.path.join(d, "job.json"), "w", encoding="utf-8") as f:
        json.dump({"id": "dead", "kind": "train_lgbm", "title": "dead", "status": "running", "createdEpoch": time.time() - 999,
                   "heartbeatEpoch": time.time() - 999, "pipeline": {"id": pid, "name": "p", "stage": "train", "index": 0, "total": 2}}, f)
    waiting = jobs._create("train_lgbm", "next", {"data": [], "out": str(results / "n.txt")},
                           pipeline={"id": pid, "name": "p", "stage": "match", "index": 1, "total": 2})
    jobs.start_next()
    job = jobs.read_job(waiting)
    assert job["state"] == "cancelled" and job["result"]["stoppedBy"] == "dead" and job["result"]["stoppedByState"] == "interrupted"


def test_eta_uses_recent_speed_and_waits_for_enough_progress():
    def g(t, n):
        return {"stage": "games", "done": n, "total": 1000, "t": t}
    assert jobs.eta_seconds([]) is None
    assert jobs.eta_seconds([g(0, 10), g(10, 20)]) is None  # under 3%... 2%
    slow_then_fast = [g(0, 0), g(100, 100), g(200, 300), g(300, 600), g(400, 900)]
    assert jobs.eta_seconds(slow_then_fast) == pytest.approx(100 * 100 / 300)  # latest window: 300 games per 100 s
    assert jobs.eta_seconds(slow_then_fast + [g(430, 1000)]) is None  # finished
    assert jobs.eta_seconds([g(0, 0), g(100, 100)], now_epoch=140) == pytest.approx(900 - 40)
