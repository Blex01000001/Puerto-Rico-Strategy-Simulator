"""Background jobs for the ML UI: each job runs in its own process, independent of the UI.

A job lives in results/ml/jobs/<id>/:
  job.json     spec + status (waiting/queued/running/done/failed/cancelled), written by the runner
  events.jsonl progress events (one JSON object per line: loaded / iteration / epoch / done)
  log.txt      text log
  cancel       created by the UI to ask the job to stop
The runner (job_runner.py) refreshes job.json["heartbeat"] every few seconds; a "running" job whose heartbeat is older
than HEARTBEAT_STALE seconds died without saying so (machine slept, process killed) and is shown as "interrupted".
Closing the UI (or the browser) does not stop a job: the process is started in its own session / process group,
so Ctrl+C in the UI's terminal does not reach it either.

Queue: one job runs at a time; jobs added meanwhile wait ("waiting") and run in the order they were added. Whenever a job
ends (done, failed or cancelled) its runner starts the next waiting one (start_next), so the queue keeps going with the
UI closed; a job that dies without ending cleanly (machine asleep, process killed) is picked up by the UI, which also
calls start_next. A lock file (results/ml/jobs/.dispatch.lock) makes sure two processes never start jobs at once.
"""
import datetime
import json
import os
import subprocess
import sys
import time
import uuid

ML_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ML_DIR)
HEARTBEAT_SECONDS = 2
HEARTBEAT_STALE = 30
KINDS = ("train_lgbm", "train_mlp", "dump", "match")


def results_dir():
    """results/ of the project; PR_RESULTS_DIR overrides it (same role as the Dashboard's ResultsDirectory setting)."""
    return os.environ.get("PR_RESULTS_DIR") or os.path.join(ROOT, "results")


def jobs_dir():
    return os.path.join(results_dir(), "ml", "jobs")


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)  # atomic: the UI never reads half a file


def read_job(job_id):
    path = os.path.join(jobs_dir(), job_id, "job.json")
    for _ in range(3):
        try:
            with open(path, encoding="utf-8") as f:
                job = json.load(f)
            break
        except (json.JSONDecodeError, FileNotFoundError):
            time.sleep(0.05)
    else:
        return None
    job["state"] = state_of(job)
    return job


def state_of(job):
    """Status as the UI should show it: a running job with a stale heartbeat was interrupted."""
    status = job.get("status")
    if status in ("queued", "running"):
        beat = job.get("heartbeatEpoch") or job.get("createdEpoch") or 0
        if time.time() - beat > HEARTBEAT_STALE:
            return "interrupted"
    return status


def list_jobs():
    """All jobs, newest first."""
    if not os.path.isdir(jobs_dir()):
        return []
    jobs = [read_job(j) for j in os.listdir(jobs_dir()) if os.path.isfile(os.path.join(jobs_dir(), j, "job.json"))]
    return sorted([j for j in jobs if j], key=lambda j: j.get("createdEpoch", 0), reverse=True)


def active_job():
    """The job that is starting or running (at most one), or None."""
    return next((j for j in list_jobs() if j["state"] in ("queued", "running")), None)


def waiting_jobs():
    """Jobs in the queue, in the order they will run."""
    return sorted((j for j in list_jobs() if j["state"] == "waiting"), key=lambda j: (j.get("createdEpoch", 0), j["id"]))


class _DispatchLock:
    """Cross-process lock (exclusive file creation); a lock older than 60 s is from a dead process and is taken over."""

    def __enter__(self):
        os.makedirs(jobs_dir(), exist_ok=True)
        self.path = os.path.join(jobs_dir(), ".dispatch.lock")
        deadline = time.time() + 30
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > 60:
                        os.remove(self.path)
                        continue
                except OSError:
                    continue
                if time.time() > deadline:
                    raise TimeoutError("job queue lock is busy") from None
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass


def start(kind, title, spec):
    """Adds a job and returns its id: it starts at once when nothing is running, otherwise it waits in the queue."""
    if kind not in KINDS:
        raise ValueError(f"unknown job kind {kind!r}")
    job_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job_dir = os.path.join(jobs_dir(), job_id)
    os.makedirs(job_dir)
    job = {"id": job_id, "kind": kind, "title": title, "spec": spec, "status": "waiting",
           "created": now(), "createdEpoch": time.time()}
    _write_json(os.path.join(job_dir, "job.json"), job)
    start_next()
    return job_id


def start_next():
    """Starts the oldest waiting job when no job is starting or running. Returns its id, or None.

    Called after every job (by its runner, whatever the outcome) and by the UI; safe to call from several processes.
    """
    with _DispatchLock():
        if active_job():
            return None
        queue = waiting_jobs()
        if not queue:
            return None
        job = read_job(queue[0]["id"])
        job.pop("state", None)
        job.update(status="queued", heartbeatEpoch=time.time())
        _write_json(os.path.join(jobs_dir(), job["id"], "job.json"), job)
        _spawn(job["id"])
        return job["id"]


def queue_position(job_id):
    """1 for the next job to run, 2 for the one after it, ...; None when the job is not waiting."""
    ids = [j["id"] for j in waiting_jobs()]
    return ids.index(job_id) + 1 if job_id in ids else None


def _spawn(job_id):
    job_dir = os.path.join(jobs_dir(), job_id)
    log = open(os.path.join(job_dir, "log.txt"), "a", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # the log file is UTF-8 whatever the Windows code page
    kwargs = {"cwd": ROOT, "stdout": log, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL, "env": env}
    if os.name == "nt":
        # own process group and no console: Ctrl+C or closing the UI's console window does not reach the job
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, os.path.join(ML_DIR, "job_runner.py"), job_dir], **kwargs)
    log.close()
    return job_id


def cancel(job_id):
    """A waiting job leaves the queue at once; a running job is asked to stop (the runner notices within HEARTBEAT_SECONDS)
    and then starts the next waiting job itself."""
    with _DispatchLock():
        job = read_job(job_id)
        if job and job["state"] == "waiting":
            job.pop("state", None)
            job.update(status="cancelled", finished=now(), result={"summary": "removed from the queue before it started"})
            _write_json(os.path.join(jobs_dir(), job_id, "job.json"), job)
            return
    open(os.path.join(jobs_dir(), job_id, "cancel"), "w").close()


def events(job_id):
    path = os.path.join(jobs_dir(), job_id, "events.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # line still being written
    return out


def log_tail(job_id, lines=40):
    path = os.path.join(jobs_dir(), job_id, "log.txt")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        return "".join(f.readlines()[-lines:])


def wait(job_id, timeout=600):
    """Blocks until the job has ended (not waiting, starting or running) (tests and scripts)."""
    end = time.time() + timeout
    while time.time() < end:
        job = read_job(job_id)
        if job and job["state"] not in ("waiting", "queued", "running"):
            return job
        time.sleep(0.2)
    raise TimeoutError(job_id)
