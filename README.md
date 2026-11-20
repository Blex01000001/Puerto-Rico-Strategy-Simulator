# Puerto Rico Strategy Simulator

**English** | [繁體中文](README.zh-TW.md)

A research tool that uses large-scale Monte Carlo simulation, tree search and machine learning to look for the strongest strategies in the board game *Puerto Rico* (base game, 4-player focus). It runs hundreds of thousands of automated games between different strategy architectures, attributes wins to strategies, and trains stronger AI models through self-play iteration. It is not a playable game and has no player interface.

**Deterministic & reproducible**: with the same config, master seed and rules revision, multi-threaded simulation produces **exactly the same results game by game**, regardless of the thread count. The rules engine and the hand-written strategies are identical on Windows and Linux (every commit is checked on both with golden-sample tests). MCTS with a value model involves floating-point arithmetic: it reproduces exactly on the same platform and version, but across platforms the last floating-point digit may differ.

The full rules the engine implements are in [`rules.md`](rules.md) (Traditional Chinese only). Every interpretation the engine had to make where the rules are ambiguous has been checked against the official rulebook ([`docs/rules-interpretations.md`](docs/rules-interpretations.md)).


## Core AI decision architecture

The simulator implements two "search + learning" hybrids, to compare a tabular-feature model (GBDT) with a feed-forward neural network (MLP) in a multi-player resource-management game:

### 1. MCTS + GBDT position evaluation (value-only approximation)

This architecture uses **Monte Carlo Tree Search (MCTS with UCT selection)** as the look-ahead planner and a **gradient-boosted decision tree (GBDT)** as the static value function at leaf nodes, replacing random rollouts, which are expensive and high-variance. When the search reaches a leaf, the value model predicts the outcome (expected win and rank) from each seat's point of view directly.

* **Training**: offline, in Python, with Microsoft's open-source **LightGBM**.
* **Pure C#, zero-dependency inference**: no native DLLs. The engine parses the exported LightGBM model and turns all tree nodes into **flat numeric arrays** in contiguous memory for lock-free inference. Results match Python's native predictions **numerically** (unit tests check this within a tolerance).
* **Speed**: evaluating a full position for 4 seats (400 trees) takes about **20 µs** on a CPU, comparable to one lightweight 8-round random rollout.
* **Deterministic compute budget**: the search budget is a fixed **simulation count**, never wall-clock time, so results do not depend on hardware load or thread count, and reproduce exactly on the same platform and version (see the note above for cross-platform floating-point differences).

### 2. MCTS + MLP position evaluation (value-only approximation)

This architecture is equivalent to the GBDT one in search framework and role. It uses the same **MCTS with UCT selection (exploration constant $c$ defaults to `0.7`)** as the planner, and a **single-head value multi-layer perceptron (MLP)** as the static value function at leaf nodes, again replacing random rollouts. There is no policy head and no PUCT search, so no fixed action encoding, legal-action masking or softmax is needed: the network only predicts the outcome from each seat's point of view.

* **Network and training**: a plain feed-forward MLP backbone (two hidden layers of 256-128 by default, **ReLU** activations) with a single value output squashed to $(0, 1)$ by a **sigmoid**. It is trained offline in Python (PyTorch or a pure NumPy implementation) with a cross-entropy loss on soft labels in $[0, 1]$.
* **Pure C#, zero-dependency inference**: no ONNX Runtime and no native DLLs. The engine reads the JSON weight file exported from Python and runs fixed-order matrix multiply-accumulate on plain arrays. Results match Python's native predictions **numerically** (unit tests check this within a tolerance).
* **Light inference and deterministic budget**: the small fully connected network is cheap on a CPU (measured at roughly 1/1.5 to 1/3 of the GBDT's speed, see the model overview below). The search budget is again a fixed simulation count, so results do not depend on hardware load or thread count, and reproduce exactly on the same platform and version.

## Training pipeline and self-play iteration

An end-to-end loop of data generation, training and match evaluation. Every step can be run from the built-in **ML UI** (a job queue and model manager) without editing code:

1. **Data generation**: the Runner plays full games with hand-written (heuristic) strategies mixed with random players. At each decision point it samples a position with probability `1% ~ 5%` (as low as `0.1%` in local experiments) and records the board features (global resources, each player's board, current score and rank). When the game ends, each seat's final result (win and rank) is written back as the training label.
2. **Training**: a LightGBM regressor fits the labels (400 trees with 63 leaves each by default; a 10% validation set split strictly by game ID to prevent leakage; early stopping).
3. **Benchmark evaluation**: the trained value model is plugged into MCTS and played against the "plain MCTS" (300 simulations, random rollouts cut at 8 rounds) and several hand-written strategies, with a **seat-balanced** layout that removes first-seat bias. **Models are judged only by match win rate**; validation error (e.g. $R^2$) is just a sanity check that training behaved.
4. **Self-play iteration**: the strongest current model drives MCTS in self-play, collecting the positions that only occur in high-level games. The new data is merged with the old, a new model is trained, and the loop goes back to step 3.
5. **Artifact hashing**: every dataset, model and match report has a content hash covering the rules version, strategy versions, all hyper-parameters and seeds, so experiment versions can be compared exactly and stale artifacts are recognised automatically.

## Current machine-learning models
All numbers are for the **4-player game**. Every model is evaluated with exactly the same benchmark setup and a seat-balanced layout:

* **Against plain MCTS**: model-guided MCTS (300 simulations) against plain MCTS (300 simulations, rollouts cut at 8 rounds), with the hand-written `cheap-engine` and `build-first` at the same table; **240 games** in total (random expectation in a 4-player game is 25%).
* **Against hand-written strategies**: `corn-shipper`, `corn-to-premium` and `build-first` at the same table, **408 games** in total; for reference, plain MCTS wins **84.9%** in this setup.
* **Significance**: the number after each win rate is the **95% confidence interval**; two win rates that fall inside each other's interval are treated as equally strong.

| Model | Training data (source and rows) | vs plain MCTS | vs hand-written | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `4p-v1` | Three hand-written strategies mixed with four random players, 20,000 games each (80,000 in total), 1% sampling; 2.08 M rows | 52.3% ± 6.3% | — | Hand-written data only: high average score, but in matches it only ties plain MCTS |
| `4p-v2` | `v1` data + **self-play 1** (four "MCTS + v1" players, 100 simulations, 4,000 games, 5% sampling; 0.49 M rows); 2.57 M rows | **68.1% ± 5.9%** | **94.6% ± 2.2%** | One round of self-play data lifts the win rate sharply; holds with a different seed (64.8%); in a roughly equal-time comparison (the model gets only 180 simulations) it still reaches 65.0% |
| `4p-v3` | `v2` data + **self-play 2** (generated by `v2`); 3.41 M rows | 66.9% ± 6.0% | 91.2% ± 2.8% | Head to head against `v2`: 49.0% vs 49.4%, no further significant gain |
| `4p-v4-hq` | `v3` data + **high-quality self-play** (`v2` against itself, 300 simulations, 20,000 games, 2% sampling) | 69.4% ± 5.8% | 90.7% ± 2.8% | Head to head against `v3` (1,440 games): 51.0% vs 47.7%, not significant; local experiment model (not in Git) |
| `4p-mlp-v2` (MLP) | Same as `v2` | 66.5% ± 6.0% | — | Neural-network baseline: as strong as LightGBM in matches, but about 1.5 to 3 times slower per CPU inference |

> Note: all numbers above were measured under rules revision 1 (see section 10 of [`docs/strategy-analysis.md`](docs/strategy-analysis.md)).

### Key findings and next steps

* **Coverage of the data distribution decides the result**: `v1`, trained on hand-written games only, merely ties plain MCTS; after one round of self-play data, `v2` leads by a wide margin. But training on self-play data **alone** (0.49 M rows) drops the win rate to `41.0%`. Early hand-written/random games provide broad coverage of the state space, while self-play data describes the state distribution of high-level play precisely; the combination works best.
* **Current features and model capacity are at diminishing returns**: 10× more hand-written data, a second self-play round (`v3`), deeper self-play search (`v4-hq`) and a bigger tree model (800 trees, 127 leaves; a tie with the original in a roughly equal-time comparison) all change the win rate only within the error margin. With the current feature set the 4-player model is close to its ceiling; **the next step is richer feature engineering** (for example predicting the opponents' intent: "which role will the next opponent most likely pick") and a larger search budget.
* **3-player models**: the 3-player models (`3p-v1` to `3p-v3`) are still weak; research effort currently goes to the 4-player game and 3-player work is on hold.
* **Offline metrics and match strength diverge**: validation $R^2$ does not rise monotonically with match win rate, so model iteration is judged strictly by **seat-balanced match win rate**.

For the full development log and parameters of every model see [`docs/models.md`](docs/models.md); for the experiment analysis see section 10 of [`docs/strategy-analysis.md`](docs/strategy-analysis.md).

## Hand-written strategies

| Name | Style |
|---|---|
| `corn-shipper` | Corn shipping: plenty of corn, ship corn every time, buy only a few useful buildings |
| `corn-to-premium` | Corn early, then tobacco/coffee in mid-game, build the matching production buildings and sell to the trading house for coins |
| `harbor-rush` | Build the Harbor first (+1 VP per shipment), then score through many shipments of several kinds of goods |
| `build-first` | Turn coins into buildings as fast as possible, aiming at large buildings with end-game bonuses |
| `cheap-engine` | Distilled from MCTS play: cheap buildings early, few plantations, frequent small shipments |
| `wharf-rush` | Farm first, then buy the Wharf, and ship the biggest pile on the private ship every time (about 16–19% in 4-player, about 41% in 3-player; MCTS sparring shows the Wharf is not that strong, see section 7 of `docs/strategy-analysis.md`) |
| `wharf-premium` | Wharf variant: sell tobacco/coffee for money first, then buy the Wharf (no better than wharf-rush, analysis 7.5) |
| `corn-monopoly` | Spoiler: corners corn, hoards it and never ships, just takes part (a corn-shipper at the same table wins about 11–27 percentage points less) |
| `corn-monopoly-tiles`, `corn-monopoly-hoard` | Two variants of the monopoly style (only grab plantations / only hoard goods) that separate the two ways of spoiling (analysis 7.4) |
| `random`, `guided-random` | Random baseline / random weighted by action type |

In addition, `mcts` is a UCT tree search (simulation count only, no time limit) that can use the value models above (the `valueModel` parameter).

## Quick start

Requires the .NET 8 SDK.

```bash
dotnet build -c Release
dotnet test -c Release
```

Run a simulation (the Runner can run for a long time; Ctrl+C writes the current result, and `--resume` continues):

```bash
dotnet run -c Release --project Runner -- --config config.strategies-compare.json --games 100000 --out result.json
```

Open the Dashboard (dark UI at http://localhost:5080, reads the `results/` folder; English by default, the language button at the bottom of the left menu switches to Traditional Chinese):

```bash
dotnet run -c Release --project Dashboard
```

> If the Dashboard looks unstyled, force-refresh with Ctrl+F5. The Dashboard and the ML UI can read any path on the server, so use them on localhost only.

Machine learning (the ML UI, which trains the position-value models for MCTS) needs Python 3. **On a new machine, run this once from the project root first:**

```bash
python -m pip install -r ml/requirements.txt
```

(Use `python -m pip` rather than plain `pip`: with several Pythons installed, e.g. Anaconda and python.org, `pip` may install into a different one.) Then start the ML UI from the "Machine learning" item in the Dashboard's left menu by clicking "ML UI not running ○" (on Windows a cmd window opens; once started it turns into a green "ML UI running ●"), or run `ml/start-ui.cmd` (Windows) / `ml/start-ui.sh` yourself. When a package is missing, both show which Python is used and the exact command to run. The ML UI is also English by default and can switch to Traditional Chinese. See `ml/README.md` for details and `docs/models.md` for the development log of each model.

### Dashboard features

| Page | Purpose |
|---|---|
| HOME | Introduction and descriptions of each strategy style |
| Simulate | Pick strategies, number of games and seed; run a normal match or a parameter sweep |
| Results | Full analysis of one result file: win rates with confidence intervals, score breakdown, buildings vs win rate, governors, end-game reasons; the "game list" at the bottom lets you browse and filter games (round, winner, margin, player score/buildings…) and jump to the replay |
| Overview | Aggregates several result files into each strategy's average win rate and a pairwise matrix |
| Compare | Two result files side by side, to see whether a win-rate difference is significant |
| Replay | Replays one game step by step with the board (player cards arranged around the supply in turn order) and an explanation of every action; for MCTS players it also lists visits and mean reward of every legal action |
| Parameter sweep | Vary one strategy parameter against fixed opponents to find better values |
| Config | Edit and validate simulation configs (JSON) |
| Version control | Rules version, engine version, each strategy's version and what each version changed |

### Configs and reproducing experiments

- Config examples: `config.example.json` (3 players), `config.4p.example.json`, `config.sweep.example.json`; the Runner and the Dashboard share one JSON format.
- Configs of each tournament and tuning round: `tournaments/` (re-run with `tournaments/run.sh`), `sweeps/`, `mcts/`; output goes to the git-ignored `results/`.
