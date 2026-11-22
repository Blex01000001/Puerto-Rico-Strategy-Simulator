"""Pure helpers of the ML UI pipeline form (no Streamlit, so they are tested on their own).

The form has three lists of rows: data (pl-d<i>-*), models to train (pl-t<i>-*) and matches (pl-m<i>-*); the row counts are
pl-d-n, pl-t-n and pl-m-n. A training row names its data and a match row its model with tokens: "new:<k>" is row k of the list
before it in this pipeline (data row k / training row k), anything else is an existing file (training) or model (match).
"""

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
