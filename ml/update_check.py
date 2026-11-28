"""Lists the ML UI jobs that are running or waiting (used by ml/update.cmd before it updates the program).

    python ml/update_check.py       (exit code 0 = no job, 2 = at least one job is running or waiting)

No Streamlit needed: only jobs.py (standard library). PR_RESULTS_DIR is honoured like everywhere else."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import jobs  # noqa: E402


def main():
    busy = [j for j in jobs.list_jobs() if j["state"] in jobs.BUSY or j["state"] == "waiting"]
    for j in busy:
        print(f'  {j["state"]:8} {j.get("title") or j["id"]}')
    return 2 if busy else 0


if __name__ == "__main__":
    sys.exit(main())
