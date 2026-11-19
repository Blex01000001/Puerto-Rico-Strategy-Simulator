# Puerto Rico Strategy Simulator 1.0.0 — release notes (draft)

Simulates the base game of Puerto Rico (3 and 4 players, no expansions) at scale to find strong strategies: a rules engine, hand-written and search-based strategies (MCTS, optionally guided by a learned value model), a command-line runner, a Blazor dashboard and a Python ML UI. It is a research tool, not a playable game.

## What 1.0.0 promises

From 1.0.0 on, the following stay backward compatible; breaking any of them is a **major** version:

- the **config and result JSON formats** (`schemaVersion`), including files written by earlier 1.x versions;
- the **command line** of the Runner (`--config --games --seed --threads --out --resume --replay --sweep --dump-positions --dump-rate`);
- the **position-dump and model formats**: feature sets coexist (`FeaturesV1`, `FeaturesV2`, …), a model records the feature names it was trained with, and older models and data keep working;
- **reproducibility**: the same config, the same seed and the same rules revision give exactly the same results, on any machine and any thread count.

Rule changes are not API breaks: they bump the **rules revision** (`base-vN`), which is part of every data/model/match hash, so old data is recognised as old instead of silently mixed with new data. Strategy decisions have their own per-strategy revisions.

## Rules (rules revision 2)

Rules are taken from `rules.md`; every interpretation the engine had to make was confirmed against the official rules and FAQ (`docs/rules-interpretations.md`). Revision 2 (engine 0.6.0) corrected three of them:

- **Factory** counts only the kinds of goods the player actually received from the supply (an empty supply on your turn means that kind does not count).
- **Craftsman privilege** is optional (you may decline) and can only take a good you produce and that still has a barrel in the supply after your normal production.
- **Warehouse storage** is a maximum: the player may keep fewer kinds, even none, and may keep no free barrel.

Everything generated before revision 2 (data, models, tournament results, the numbers in `docs/strategy-analysis.md`) was produced under revision 1 and is marked "old" in both UIs. The effect is small (the changed situations are rare), but results must be regenerated before they are compared with new ones.

## Tools

- **Runner**: batch simulation, resume, replay, parameter sweeps, position dumps for training.
- **Dashboard** (Blazor, English by default, Traditional Chinese switchable): simulate, results, tournaments overview, A/B comparison, step-by-step replay with the MCTS search shown, parameter sweeps, config editor, version control page.
- **ML UI** (Streamlit, English by default, Traditional Chinese switchable): data sampling, LightGBM/MLP training, match validation, model list, job queue, hashes of every dataset/model/match.
- **Version control**: rules, engine, feature, data-format and per-strategy versions with change logs (`docs/versions.json`), checked by golden-sample tests.

## Known limitations

- Base game only: 3 and 4 players; no expansions, no 5-player games.
- The value models, tuning and most analysis target the **4-player** game; 3-player models are older and weaker.
- Hidden information (opponents' VP chips) is protected by convention only; strategies are trusted not to read it.
- The Dashboard and the ML UI are meant for **localhost only**: they can read arbitrary paths on the machine they run on.
- Windows: the full .NET test suite (including the golden-sample hashes, so results are identical to Linux) and the Python suite (including real background-job processes) pass on `windows-latest` in CI. Cancelling a data-generation job on Windows ends the Runner outright, so the games finished so far are not kept (Linux keeps them). Nobody has driven the ML UI by hand on Windows yet.

## Upgrading

- Result files, configs and dumps written by 0.x versions still load; resuming a run (`--resume`) is refused when the rules revision or a strategy revision differs.
- Re-generate datasets and re-train models to get ones under rules revision 2.
