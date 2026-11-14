"""Runs one ML UI job in its own process (started by jobs.start; not meant to be run by hand).

    python3 ml/job_runner.py <job directory>

Job kinds:
  train_lgbm / train_mlp  train a model (train_lgbm.train / train_mlp.train); cancel = end the process
  dump                    Runner --dump-positions (training data)
  match                   Runner match; the result is recorded in the model's .meta.json (modelmeta.add_match)
Runner jobs use the published Runner (publish/runner, or PR_RUNNER_DIR) and publish it first when the C# sources are
newer. Cancelling a Runner job sends it Ctrl+C (SIGINT; on Windows the process is ended), so a dump keeps the games
already done and a match writes a partial result.
"""
import glob
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jobs  # noqa: E402

PROGRESS = re.compile(r"(\d+)/(\d+) games")


class Job:
    def __init__(self, job_dir):
        self.dir = job_dir
        self.path = os.path.join(job_dir, "job.json")
        with open(self.path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.lock = threading.Lock()
        self.events = open(os.path.join(job_dir, "events.jsonl"), "a", encoding="utf-8")
        self.child = None          # Runner process, if any
        self.cancelling = False

    def update(self, **fields):
        with self.lock:
            self.data.update(fields)
            self.data["heartbeatEpoch"] = time.time()
            jobs._write_json(self.path, self.data)

    def event(self, ev):
        with self.lock:
            self.events.write(json.dumps({**ev, "t": round(time.time(), 2)}) + "\n")
            self.events.flush()

    def cancel_requested(self):
        return os.path.exists(os.path.join(self.dir, "cancel"))


class Cancelled(Exception):
    pass


def heartbeat(job, stop):
    """Keeps the heartbeat fresh and reacts to the cancel flag (same on Windows and Linux)."""
    while not stop.wait(jobs.HEARTBEAT_SECONDS):
        if job.cancel_requested() and not job.cancelling:
            job.cancelling = True
            print("cancel requested by the user", flush=True)
            if job.child is None:
                job.update(status="cancelled", finished=jobs.now())
                os._exit(130)  # training: stop wherever it is; models are only written at the end
            stop_child(job.child)
        job.update()


def stop_child(proc):
    """Ctrl+C for the Runner so it writes what it has; ends it if it does not stop in time."""
    try:
        if os.name == "nt":
            proc.terminate()  # no shared console to deliver Ctrl+C to: partial output is lost on Windows
        else:
            proc.send_signal(signal.SIGINT)
    except OSError:
        return

    def kill_later():
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
    threading.Thread(target=kill_later, daemon=True).start()


# ---------------------------------------------------------------- Runner

def runner_dir():
    return os.environ.get("PR_RUNNER_DIR") or os.path.join(jobs.ROOT, "publish", "runner")


def sources_newer_than(path):
    """True when a C# source of Engine/Runner (or the build settings) changed after `path` was written."""
    if not os.path.exists(path):
        return True
    built = os.path.getmtime(path)
    patterns = ["Engine/**/*.cs", "Engine/*.csproj", "Runner/**/*.cs", "Runner/*.csproj", "Directory.Build.props"]
    for pattern in patterns:
        for f in glob.glob(os.path.join(jobs.ROOT, pattern), recursive=True):
            if f"{os.sep}obj{os.sep}" in f or f"{os.sep}bin{os.sep}" in f:
                continue
            if os.path.getmtime(f) > built:
                return True
    return False


def ensure_runner(job):
    """Path of the published Runner.dll, publishing it first when it is missing or older than the sources."""
    out = runner_dir()
    dll = os.path.join(out, "Runner.dll")
    if sources_newer_than(dll):
        print(f"publishing Runner to {os.path.relpath(out, jobs.ROOT)} (missing or older than the C# sources)...", flush=True)
        job.event({"stage": "publish"})
        cmd = ["dotnet", "publish", os.path.join(jobs.ROOT, "Runner"), "-c", "Release", "-o", out, "--nologo", "-v", "q"]
        try:
            r = subprocess.run(cmd, cwd=jobs.ROOT, capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError("找不到 dotnet 指令：產生資料與對戰需要 .NET 8 SDK") from None
        print(r.stdout[-3000:], r.stderr[-3000:], flush=True)
        if r.returncode != 0:
            raise RuntimeError(f"dotnet publish failed (exit {r.returncode})")
    return dll


def run_runner(job, args):
    """Runs the Runner, turning its 'n/total games' progress into events. Returns (exit code, output lines)."""
    dll = ensure_runner(job)
    cmd = ["dotnet", dll] + args
    print("> " + " ".join(cmd), flush=True)
    kwargs = {"cwd": jobs.ROOT, "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    job.child = subprocess.Popen(cmd, **kwargs)
    lines, buf, last = [], b"", (None, 0.0)
    while True:
        chunk = job.child.stdout.read1(4096) if hasattr(job.child.stdout, "read1") else job.child.stdout.read(4096)
        if not chunk:
            break
        buf += chunk
        parts = re.split(rb"[\r\n]", buf)
        buf = parts.pop()
        for raw in parts:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            m = PROGRESS.search(line)
            if m:
                done, total = int(m.group(1)), int(m.group(2))
                if done != last[0] and (time.time() - last[1] > 1 or done == total):
                    job.event({"stage": "games", "done": done, "total": total})
                    last = (done, time.time())
                continue  # progress lines go to events, not to the log
            print(line, flush=True)
            lines.append(line)
    if buf.strip():
        lines.append(buf.decode("utf-8", errors="replace").strip())
        print(lines[-1], flush=True)
    code = job.child.wait()
    return code, lines


def run_dump(job, spec):
    args = ["--config", spec["config"], "--dump-positions", spec["out"], "--dump-rate", str(spec["rate"])]
    for key in ("games", "seed", "threads"):
        if spec.get(key) is not None:
            args += [f"--{key}", str(spec[key])]
    code, lines = run_runner(job, args)
    summary = next((l for l in reversed(lines) if " rows " in l), "")
    if code not in (0, 130) or (code == 130 and not job.cancelling):
        raise RuntimeError(f"Runner exit {code}")
    m = re.search(r"(\d+) games, (\d+) positions, (\d+) rows", summary)
    result = {"output": spec["out"], "summary": summary}
    if m:
        result.update(games=int(m.group(1)), positions=int(m.group(2)), rows=int(m.group(3)))
    if code == 130:
        raise Cancelled(result)
    return result


def run_match(job, spec):
    import modelmeta
    args = ["--config", spec["config"], "--out", spec["out"]]
    if spec.get("threads") is not None:
        args += ["--threads", str(spec["threads"])]
    code, lines = run_runner(job, args)
    if code == 130 and job.cancelling:
        raise Cancelled({"output": spec["out"], "summary": "partial result (not recorded in the model)"})
    if code != 0:
        raise RuntimeError(f"Runner exit {code}")
    entry = modelmeta.add_match(spec["model"], spec["out"])
    print(f"recorded in {spec['model']}.meta.json: win share {entry['winShare']:.1%} ± {entry['winShareCi95']:.1%}", flush=True)
    return {"output": spec["out"], "match": entry, "summary": "\n".join(l for l in lines if "win share" in l)}


def run(job):
    spec = job.data["spec"]
    kind = job.data["kind"]
    if kind in ("train_lgbm", "train_mlp"):
        trainer = __import__("train_lgbm" if kind == "train_lgbm" else "train_mlp")
        meta = trainer.train(spec["data"], spec["out"], progress=job.event, log=lambda m: print(m, flush=True), **spec.get("options", {}))
        return {"model": spec["out"], "validation": meta["validation"]}
    if kind == "dump":
        return run_dump(job, spec)
    if kind == "match":
        return run_match(job, spec)
    raise ValueError(f"unknown job kind {kind!r}")


def main():
    job = Job(sys.argv[1])
    stop = threading.Event()
    job.update(status="running", started=jobs.now(), pid=os.getpid())
    threading.Thread(target=heartbeat, args=(job, stop), daemon=True).start()
    try:
        result = run(job)
        stop.set()
        job.event({"stage": "done"})
        job.update(status="done", finished=jobs.now(), result=result)
    except Cancelled as c:
        stop.set()
        job.update(status="cancelled", finished=jobs.now(), result=c.args[0])
        sys.exit(130)
    except Exception as e:  # noqa: BLE001 - every failure must end up in job.json for the UI
        stop.set()
        traceback.print_exc()
        sys.stdout.flush()
        job.update(status="failed", finished=jobs.now(), error=f"{type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
