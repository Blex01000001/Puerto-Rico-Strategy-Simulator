"""Default training options of both model kinds and the MLP backend choice, without importing LightGBM, NumPy or PyTorch.

train_lgbm.py / train_mlp.py train with them (their DEFAULTS are these dicts); the ML UI only needs the defaults and the
resolved MLP backend, so it imports this small module instead of the training scripts. A new training option goes here
(and into fingerprint.LGBM_OPTIONS / MLP_OPTIONS or IGNORED_OPTIONS; tests/test_fingerprint.py checks it)."""

LGBM_DEFAULTS = {"rounds": 400, "leaves": 63, "lr": 0.05, "min_leaf": 200, "feature_fraction": 0.8,
                 "bagging_fraction": 0.8, "valid": 0.1, "seed": 1, "threads": 0, "early_stopping": 30}

MLP_DEFAULTS = {"hidden": "256,128", "epochs": 12, "batch": 1024, "lr": 1e-3, "l2": 1e-5, "patience": 3,
                "valid": 0.1, "seed": 1, "backend": "auto", "device": "auto"}


def defaults(kind):
    """A copy of the defaults of a job kind: "train_lgbm" or "train_mlp"."""
    return dict(LGBM_DEFAULTS if kind == "train_lgbm" else MLP_DEFAULTS)


def resolve_backend(o):
    """(backend, device) an MLP run with these options really uses ('auto' resolved the way train_mlp.train() does)."""
    backend = o["backend"]
    if backend == "auto":
        backend = "torch" if torch_available() else "numpy"
    if backend != "torch":
        return backend, "cpu"
    device = o["device"]
    if device == "auto":
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    return backend, device


def torch_available():
    try:
        import torch  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 - a broken install (e.g. missing CUDA libraries) counts as unavailable
        return False
