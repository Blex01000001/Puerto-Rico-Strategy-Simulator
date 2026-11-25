"""Background jobs for the ML UI: each job runs in its own process, independent of the UI.

A job lives in results/ml/jobs/<id>/:
  job.json     spec + status (waiting/queued/running/done/failed/cancelled), written by the runner
  events.jsonl progress events (one JSON object per line: loaded / iteration / epoch / done)
  log.txt      text log
  cancel       created by the UI to ask the job to stop
The runner (job_runner.py) refreshes job.json["heartbeat"] every few seconds; a "running" job whose heartbeat is older
than HEARTBEAT_STALE seconds is either "lost" (its process is still alive: the heartbeat stopped but the work may go on;
the queue waits for it) or "interrupted" (the process is gone: machine slept, process killed).
Closing the UI (or the browser) does not stop a job: the process is started in its own session / process group,
so Ctrl+C in the UI's terminal does not reach it either.

Queue: one job runs at a time; jobs added meanwhile wait ("waiting") and run in the order they were added. Whenever a job
ends (done, failed or cancelled) its runner starts the next waiting one (start_next), so the queue keeps going with the
UI closed; a job that dies without ending cleanly (machine asleep, process killed) is picked up by the UI, which also
calls start_next. A lock file (results/ml/jobs/.dispatch.lock) makes sure two processes never start jobs at once.

Pipeline: jobs added together with start_pipeline (job.json "pipeline": {id, name, stage, index, total}) run in the order given,
like any queued jobs. When any job of a pipeline fails, is cancelled or is interrupted, every job of that pipeline that has not
started is cancelled too ("stoppedBy" = the job that broke it); files already written stay. This is decided here (start_next,
cancel), not in the UI, so it also holds with the UI closed.
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


def _write_json(path, data, tries=100):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # atomic: the UI never reads half a file. On Windows the replace fails with PermissionError while another process
    # (the UI polling every 2 s, an antivirus or the search indexer) has the file open: retry for a few seconds.
    for i in range(tries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05)


def read_job(job_id):
    path = os.path.join(jobs_dir(), job_id, "job.json")
    for _ in range(3):
        try:
            with open(path, encoding="utf-8") as f:
                job = json.load(f)
            break
        except (json.JSONDecodeError, FileNotFoundError, PermissionError):  # PermissionError: Windows, mid-replace
            time.sleep(0.05)
    else:
        return None
    job["state"] = state_of(job)
    return job


def state_of(job):
    """Status as the UI should show it: a running job with a stale heartbeat is "lost" while its process is still alive
    (the queue keeps waiting for it) and "interrupted" once it is gone."""
    status = job.get("status")
    if status in ("queued", "running"):
        beat = job.get("heartbeatEpoch") or job.get("createdEpoch") or 0
        if time.time() - beat > HEARTBEAT_STALE:
            return "lost" if process_alive(job) else "interrupted"
    return status


# states in which a job occupies the queue (nothing else may start)
BUSY = ("queued", "running", "lost")


def process_alive(job):
    """True when the job's runner process (job.json "pid", written when it starts) still runs. The process must also be
    a Python started no later than the job, so a recycled pid of some other program does not count."""
    pid = job.get("pid")
    if not pid:
        return False
    started = job.get("startedEpoch")
    try:
        if os.name == "nt":
            return _alive_windows(int(pid), started)
        return _alive_posix(int(pid), started)
    except (OSError, ValueError):
        return False


def _alive_posix(pid, started):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # exists, owned by someone else
    stat_path = f"/proc/{pid}/stat"
    if not os.path.exists(stat_path):
        return True  # no /proc (macOS): trust the signal check
    with open(stat_path, encoding="utf-8", errors="replace") as f:
        fields = f.read().rsplit(")", 1)[1].split()
    if fields[0] == "Z":
        return False  # zombie: it has ended, only its parent has not collected it
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if b"job_runner" not in f.read():
                return False  # the pid now belongs to another program
    except OSError:
        pass
    if started:
        with open("/proc/stat", encoding="utf-8") as f:
            boot = next(int(line.split()[1]) for line in f if line.startswith("btime"))
        created = boot + int(fields[19]) / os.sysconf("SC_CLK_TCK")
        return created <= started + 5
    return True


def _alive_windows(pid, started):
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5  # access denied: it exists
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
            return False
        name = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if k32.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)) and "python" not in name.value.lower():
            return False  # the pid now belongs to another program
        created = None
        times = [wintypes.FILETIME() for _ in range(4)]
        if k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
            ft = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            created = ft / 1e7 - 11644473600  # FILETIME (100 ns since 1601) -> Unix time
            if started and created > started + 5:
                return False
        # any Python started before the job could still be another program (pytest, a notebook): the command line must name job_runner
        line = _windows_command_line(pid, created)
        return line is None or "job_runner" in line  # None: it could not be read, trust the checks above
    finally:
        k32.CloseHandle(handle)


_CMDLINES = {}


def _windows_command_line(pid, created):
    """Command line of a process (PowerShell/CIM), cached per (pid, start time) since it never changes; None when unreadable."""
    key = (pid, created)
    if key not in _CMDLINES:
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                  f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"],
                                 capture_output=True, text=True, timeout=20)
            _CMDLINES[key] = out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None
        except (OSError, subprocess.SubprocessError):
            _CMDLINES[key] = None
    return _CMDLINES[key]


def relpath(path, start=None):
    """os.path.relpath that does not fail when the two paths are on different drives (Windows): then the path is returned as is."""
    try:
        return os.path.relpath(path, start or ROOT)
    except ValueError:
        return path


def force_stop(job):
    """Ends a lost job's runner and everything it started (the Runner), then marks it cancelled."""
    pid = int(job["pid"])
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        import signal
        try:
            os.killpg(pid, signal.SIGTERM)  # the runner leads its own session: its Runner child is in the same group
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    job = {k: v for k, v in job.items() if k != "state"}
    job.update(status="cancelled", finished=now(), result={"summary": "stopped by the user after the heartbeat was lost"})
    _write_json(os.path.join(jobs_dir(), job["id"], "job.json"), job)


def list_jobs():
    """All jobs, newest first."""
    if not os.path.isdir(jobs_dir()):
        return []
    jobs = [read_job(j) for j in os.listdir(jobs_dir()) if os.path.isfile(os.path.join(jobs_dir(), j, "job.json"))]
    return sorted([j for j in jobs if j], key=lambda j: j.get("createdEpoch", 0), reverse=True)


def active_job():
    """The job that is starting, running or lost (at most one), or None: while there is one, nothing else starts."""
    return next((j for j in list_jobs() if j["state"] in BUSY), None)


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


def _create(kind, title, spec, title_key=None, title_args=None, pipeline=None, created_epoch=None):
    """Writes a waiting job (does not start anything) and returns its id."""
    if kind not in KINDS:
        raise ValueError(f"unknown job kind {kind!r}")
    job_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job_dir = os.path.join(jobs_dir(), job_id)
    os.makedirs(job_dir)
    job = {"id": job_id, "kind": kind, "title": title, "spec": spec, "status": "waiting",
           "created": now(), "createdEpoch": created_epoch or time.time()}
    if title_key:
        job["titleKey"], job["titleArgs"] = title_key, title_args or {}
    if pipeline:
        job["pipeline"] = pipeline
    _write_json(os.path.join(job_dir, "job.json"), job)
    return job_id


def start(kind, title, spec, title_key=None, title_args=None):
    """Adds a job and returns its id: it starts at once when nothing is running, otherwise it waits in the queue.

    `title` is the text shown when nothing better is known; `title_key` + `title_args` (an i18n key and its values) let the UI show
    the title in the language it is in now (jobs written without them keep their text)."""
    job_id = _create(kind, title, spec, title_key, title_args)
    start_next()
    return job_id


def start_pipeline(name, steps):
    """Adds several jobs as one pipeline and returns their ids in run order.

    `steps`: dicts with kind, title, spec, stage ("data", "train", "match"…) and optionally titleKey / titleArgs. All jobs are written before
    anything starts, with strictly increasing creation times, so they run in the given order (the queue is first in, first out)."""
    if not steps:
        raise ValueError("a pipeline needs at least one job")
    pid = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    base = time.time()
    ids = []
    for i, step in enumerate(steps):
        ids.append(_create(step["kind"], step["title"], step["spec"], step.get("titleKey"), step.get("titleArgs"),
                           pipeline={"id": pid, "name": name, "stage": step.get("stage", ""), "index": i, "total": len(steps)},
                           created_epoch=base + i * 0.001))
    start_next()
    return ids


def pipeline_jobs(pipeline_id):
    """The jobs of a pipeline in run order."""
    return sorted((j for j in list_jobs() if (j.get("pipeline") or {}).get("id") == pipeline_id), key=lambda j: j["pipeline"]["index"])


# a job in one of these states breaks its pipeline (a cancelled job as well: the user stopped the pipeline)
PIPELINE_BREAKING = ("failed", "cancelled", "interrupted")


def _stop_broken_pipelines():
    """Cancels the waiting jobs of every pipeline that has a failed, cancelled or interrupted job. Caller holds the dispatch lock."""
    every = list_jobs()
    broken = {}
    for j in every:
        p = j.get("pipeline")
        if p and j["state"] in PIPELINE_BREAKING and p["id"] not in broken:
            broken[p["id"]] = j
    for j in every:
        p = j.get("pipeline")
        if p and j["state"] == "waiting" and p["id"] in broken:
            job = read_job(j["id"])
            job.pop("state", None)
            job.update(status="cancelled", finished=now(),
                       result={"summary": "pipeline stopped before this job started", "stoppedBy": broken[p["id"]]["id"],
                               "stoppedByState": broken[p["id"]]["state"]})
            _write_json(os.path.join(jobs_dir(), j["id"], "job.json"), job)


def start_next():
    """Starts the oldest waiting job when no job is starting or running. Returns its id, or None.

    Called after every job (by its runner, whatever the outcome) and by the UI; safe to call from several processes.
    """
    with _DispatchLock():
        _stop_broken_pipelines()
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
    and then starts the next waiting job itself; a lost job (its runner no longer reads the cancel flag) is ended here and
    the next waiting job starts."""
    job = read_job(job_id)
    if job and job["state"] == "lost":
        force_stop(job)
        start_next()
        return
    with _DispatchLock():
        job = read_job(job_id)
        if job and job["state"] == "waiting":
            job.pop("state", None)
            job.update(status="cancelled", finished=now(), result={"summary": "removed from the queue before it started"})
            _write_json(os.path.join(jobs_dir(), job_id, "job.json"), job)
            _stop_broken_pipelines()  # a pipeline job: the rest of its pipeline goes too
            return
    open(os.path.join(jobs_dir(), job_id, "cancel"), "w").close()


def cancel_pipeline(pipeline_id):
    """Stops a whole pipeline: its waiting jobs leave the queue at once, the running one is asked to stop (a lost one is ended)."""
    with _DispatchLock():
        for j in pipeline_jobs(pipeline_id):
            if j["state"] == "waiting":
                job = read_job(j["id"])
                job.pop("state", None)
                job.update(status="cancelled", finished=now(), result={"summary": "pipeline cancelled by the user"})
                _write_json(os.path.join(jobs_dir(), j["id"], "job.json"), job)
    for j in pipeline_jobs(pipeline_id):
        if j["state"] in BUSY:
            cancel(j["id"])


def eta_seconds(evs, now_epoch=None):
    """Estimated seconds left for a running job from its progress events, or None while it cannot be told yet.
    Speed comes from the latest ~30% of the observed time (the early part of a job is not representative);
    nothing is estimated before 3% progress or with fewer than two points."""
    pts = []
    for e in evs:
        if e.get("stage") == "games":
            n, total = e.get("done"), e.get("total")
        elif e.get("stage") in ("iteration", "epoch"):
            n, total = e.get("iteration") or e.get("epoch"), e.get("total")
        else:
            continue
        if n is not None and total and e.get("t") is not None:
            pts.append((e["t"], n, total))
    if len(pts) < 2:
        return None
    t_last, n_last, total = pts[-1]
    if n_last >= total or n_last / total < 0.03:
        return None
    window = [p for p in pts if p[0] >= t_last - 0.3 * (t_last - pts[0][0])]
    t0, n0, _ = window[0] if len(window) >= 2 else pts[0]
    if n_last <= n0 or t_last <= t0:
        return None
    left = (total - n_last) * (t_last - t0) / (n_last - n0)
    if now_epoch is not None:
        left -= max(0.0, now_epoch - t_last)  # time already passed since the last event
    return max(0.0, left)


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
        if job and job["state"] not in ("waiting",) + BUSY:
            return job
        time.sleep(0.2)
    raise TimeoutError(job_id)
