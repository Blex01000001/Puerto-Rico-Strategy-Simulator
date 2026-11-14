"""Runs one ML UI job in its own process (started by jobs.start; not meant to be run by hand).

    python3 ml/job_runner.py <job directory>
"""
import json
import os
import sys
import threading
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jobs  # noqa: E402


class Job:
    def __init__(self, job_dir):
        self.dir = job_dir
        self.path = os.path.join(job_dir, "job.json")
        with open(self.path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.lock = threading.Lock()
        self.events = open(os.path.join(job_dir, "events.jsonl"), "a", encoding="utf-8")

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


def heartbeat(job, stop):
    """Keeps the heartbeat fresh and ends the process when the UI asks for it (works the same on Windows and Linux)."""
    while not stop.wait(jobs.HEARTBEAT_SECONDS):
        if job.cancel_requested():
            print("cancelled by the user", flush=True)
            job.update(status="cancelled", finished=jobs.now())
            os._exit(130)  # stop the training wherever it is; nothing half-written is kept (models are saved at the end)
        job.update()


def run(job):
    spec = job.data["spec"]
    kind = job.data["kind"]
    if kind == "train_lgbm":
        import train_lgbm as trainer
    elif kind == "train_mlp":
        import train_mlp as trainer
    else:
        raise ValueError(f"unknown job kind {kind!r}")
    meta = trainer.train(spec["data"], spec["out"], progress=job.event, log=lambda m: print(m, flush=True), **spec.get("options", {}))
    return {"model": spec["out"], "validation": meta["validation"]}


def main():
    job = Job(sys.argv[1])
    stop = threading.Event()
    job.update(status="running", started=jobs.now(), pid=os.getpid())
    threading.Thread(target=heartbeat, args=(job, stop), daemon=True).start()
    try:
        result = run(job)
        stop.set()
        job.update(status="done", finished=jobs.now(), result=result)
    except Exception as e:  # noqa: BLE001 - every failure must end up in job.json for the UI
        stop.set()
        traceback.print_exc()
        sys.stdout.flush()
        job.update(status="failed", finished=jobs.now(), error=f"{type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
