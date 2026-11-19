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
        if started:
            times = [wintypes.FILETIME() for _ in range(4)]
            if k32.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                ft = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
                created = ft / 1e7 - 11644473600  # FILETIME (100 ns since 1601) -> Unix time
                return created <= started + 5
        return True
    finally:
        k32.CloseHandle(handle)


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


def start(kind, title, spec, title_key=None, title_args=None):
    """Adds a job and returns its id: it starts at once when nothing is running, otherwise it waits in the queue.

    `title` is the text shown when nothing better is known; `title_key` + `title_args` (an i18n key and its values) let the UI show
    the title in the language it is in now (jobs written without them keep their text)."""
    if kind not in KINDS:
        raise ValueError(f"unknown job kind {kind!r}")
    job_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    job_dir = os.path.join(jobs_dir(), job_id)
    os.makedirs(job_dir)
    job = {"id": job_id, "kind": kind, "title": title, "spec": spec, "status": "waiting",
           "created": now(), "createdEpoch": time.time()}
    if title_key:
        job["titleKey"], job["titleArgs"] = title_key, title_args or {}
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
        if job and job["state"] not in ("waiting",) + BUSY:
            return job
        time.sleep(0.2)
    raise TimeoutError(job_id)
