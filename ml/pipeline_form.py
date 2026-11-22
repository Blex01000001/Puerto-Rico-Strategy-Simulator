"""Pure helpers of the ML UI pipeline form (no Streamlit, so they are tested on their own).

The form keeps three lists of items (dicts, set up in a dialog and shown read-only on the page): data ("pl-data"), models to train
("pl-train") and matches ("pl-match"). A training item names its data and a match item its model with tokens: "new:<k>" is item k of the
list before it in this pipeline (data item k / training item k), anything else is an existing file (training) or model (match).
Templates written by the first two pipeline pages (settings as one widget key per row) are converted by items_from_widget_settings.
"""
import re


NEW = "new:"


def new_token(index):
    return f"{NEW}{index}"


def token_index(token):
    """k of "new:<k>", None for an existing file or model."""
    if isinstance(token, str) and token.startswith(NEW):
        try:
            return int(token[len(NEW):])
        except ValueError:
            return None
    return None


def shift_token(token, removed):
    """The token after row `removed` of the referenced list went away (None: all rows are gone). None = the reference is dropped."""
    k = token_index(token)
    if k is None:
        return token
    if removed is None or k == removed:
        return None
    return new_token(k - 1) if k > removed else token


def shift_tokens(tokens, removed):
    return [s for s in (shift_token(tok, removed) for tok in tokens) if s is not None]


def migrate_settings(settings):
    """Settings of a template saved by the first pipeline page (one data step, one training step, a match list with one model, each step
    with an on/off box) as the settings of the multi-row form. Settings that are already in the new form are returned as they are."""
    s = dict(settings)
    if "pl-d-n" in s or "pl-t-n" in s:
        return s
    old = any(k.startswith(("pl-d-", "pl-t-")) for k in s) or "pl-m-model" in s
    if not old:
        return s
    data_on, train_on = s.get("pl-d-on", True), s.get("pl-t-on", True)
    out = {}
    for k, v in s.items():
        if k in ("pl-d-on", "pl-t-on", "pl-m-model"):
            continue
        if k.startswith("pl-d-"):
            out["pl-d0-" + k[len("pl-d-"):]] = v
        elif k.startswith("pl-t-"):
            out["pl-t0-" + k[len("pl-t-"):]] = v
        else:
            out[k] = v
    out["pl-d-n"] = 1 if data_on else 0
    out["pl-t-n"] = 1 if train_on else 0
    if train_on:
        # the new data (when step 1 was on) plus the existing files that were ticked
        existing = out.pop("pl-t0-existing", [])
        out["pl-t0-data"] = ([new_token(0)] if data_on else []) + list(existing if isinstance(existing, list) else [])
        out["pl-t0-data-for"] = "init"  # a remembered choice: the default (all new data) must not overwrite it
        # the matches of the old form all played one model: the one trained here, or the existing one that was picked
        model = new_token(0) if train_on else s.get("pl-m-model")
    else:
        model = s.get("pl-m-model")
    if model:
        for i in range(int(s.get("pl-m-n", 0) or 0)):
            out[f"pl-m{i}-model"] = model
    return out


LISTS = {"d": "pl-data", "t": "pl-train", "m": "pl-match"}


def remove_item(data, train, match, kind, index):
    """The three lists after item `index` of list `kind` ("d" data, "t" training, "m" match) was removed. Removing a model removes its
    matches; removing data only takes it out of the training items that used it. (Returns new lists.)"""
    data, train, match = list(data), list(train), list(match)
    if kind == "d":
        data.pop(index)
        train = [{**tr, "data": shift_tokens(tr.get("data", []), index)} for tr in train]
    elif kind == "t":
        train.pop(index)
        match = [{**m, "model": shift_token(m.get("model"), index)} for m in match if shift_token(m.get("model"), index) is not None]
    else:
        match.pop(index)
    return data, train, match


def clear_items(data, train, match, kind):
    """The three lists after every item of list `kind` was removed (with what depends on them)."""
    if kind == "d":
        return [], [{**tr, "data": shift_tokens(tr.get("data", []), None)} for tr in train], list(match)
    if kind == "t":
        return list(data), [], [m for m in match if token_index(m.get("model")) is None]
    return list(data), list(train), []


DATA_FIELDS = ("mode", "config", "model", "sims", "leaf", "games", "seed", "rate", "threads", "feature", "name")
MATCH_FIELDS = ("model", "table", "rival", "bsims", "games", "seed")
_ROW_KEY = re.compile(r"^pl-[dtm]\d+-")
_DROPPED = ("pl-d-n", "pl-t-n", "pl-m-n", "pl-m-sims", "pl-m-leaf", "pl-m-threads")


def items_from_widget_settings(settings):
    """A template written with one widget key per row (the first two pipeline pages) as the settings of the item lists. Settings that
    already have the lists are returned as they are."""
    if "pl-data" in settings or "pl-train" in settings or "pl-match" in settings:
        return dict(settings)
    s = migrate_settings(settings)
    data, train, match = [], [], []
    for i in range(int(s.get("pl-d-n", 0) or 0)):
        p = f"pl-d{i}-"
        data.append({f: s[p + f] for f in DATA_FIELDS if p + f in s})
    for i in range(int(s.get("pl-t-n", 0) or 0)):
        p = f"pl-t{i}-"
        kind = s.get(p + "kind", "train_lgbm")
        prefix = f"{p}opt-{kind}-"
        train.append({"data": list(s.get(p + "data", [])), "kind": kind, "name": s.get(p + "name", ""),
                      "options": {k[len(prefix):]: v for k, v in s.items() if k.startswith(prefix) and not k.endswith("-for")}})
    for i in range(int(s.get("pl-m-n", 0) or 0)):
        p = f"pl-m{i}-"
        item = {f: s[p + f] for f in MATCH_FIELDS if p + f in s}
        item.update(sims=s.get("pl-m-sims", 300), leaf=s.get("pl-m-leaf", 40), threads=s.get("pl-m-threads", 0))
        match.append(item)
    out = {k: v for k, v in s.items() if not _ROW_KEY.match(k) and k not in _DROPPED}
    out.update({"pl-data": data, "pl-train": train, "pl-match": match})
    return out
