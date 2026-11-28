"""Favorites: training data files and models the user marked with a star (the ML UI's quick filter 我的最愛).

Kept in the local workspace (ml/local/favorites.json, ignored by git, so it is per computer): {"dumps": [file names], "models": [file names]}.
A key is the file NAME (a dump's `x.bin`, a model's `x.txt`): names are unique inside results/ml and across the official and local
model folders. No Streamlit here: the pages call these functions and tests use them directly."""
import json
import os

import modelmeta

KINDS = ("dumps", "models")


def path():
    return os.path.join(modelmeta.LOCAL_DIR, "favorites.json")


def load():
    """{"dumps": set, "models": set}; empty when the file is missing or unreadable."""
    try:
        with open(path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return {k: {str(x) for x in (data.get(k) or []) if isinstance(x, str)} for k in KINDS} if isinstance(data, dict) else {k: set() for k in KINDS}


def _save(data):
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: sorted(data[k]) for k in KINDS}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path())


def names(kind):
    return load()[kind]


def is_favorite(kind, name):
    return os.path.basename(str(name)) in load()[kind]


def set_favorite(kind, items, flag):
    """Marks (flag=True) or unmarks the files `items` (names or paths)."""
    data = load()
    for x in items:
        (data[kind].add if flag else data[kind].discard)(os.path.basename(str(x)))
    _save(data)


def rename(kind, old, new):
    """A renamed file keeps its star."""
    data = load()
    old, new = os.path.basename(str(old)), os.path.basename(str(new))
    if old in data[kind]:
        data[kind].discard(old)
        data[kind].add(new)
        _save(data)


def prune(kind, existing):
    """Forgets the names that no longer exist (a deleted file must not hand its star to a new file of the same name)."""
    data = load()
    keep = {os.path.basename(str(x)) for x in existing}
    gone = data[kind] - keep
    if gone:
        data[kind] -= gone
        _save(data)
