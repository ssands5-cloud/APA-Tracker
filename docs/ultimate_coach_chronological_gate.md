# Ultimate Coach chronological archive gate

This slice establishes the leakage boundary required before future calibration work. It does **not** train a model, score a matchup, or authorize publication of odds.

## Contract

- operate on one format at a time: EIGHT or NINE;
- accept only `VERIFIED_UNIQUE` canonical All Games rows;
- require a parseable real match timestamp and known observed winner/loser;
- sort by time, never randomize;
- reserve the newest fraction as holdout;
- return exact train and holdout `game_key` values for audit;
- report every excluded evidence category;
- fail closed when verified archive or holdout size is below the configured minimum;
- always report `probability_publication = FORBIDDEN`.

`READY_FOR_BACKTEST` means only that the archive has enough structurally valid chronological evidence to run a future backtest. It is **not** a model-quality verdict and is never sufficient to publish matchup odds.

## Future calibration gate

A later independently audited slice must define candidate features using information available strictly before each predicted game's timestamp, run chronological/rolling-origin evaluation separately for 8-Ball and 9-Ball, measure discrimination and calibration on held-out real APA games, and compare against simple baselines. Probability publication remains blocked until that work passes explicit acceptance thresholds on the real archive.

## Claude audit challenge

1. Scramble input order and prove the newest rows alone enter holdout.
2. Mix EIGHT/NINE rows and prove isolation.
3. Inject `VERIFIED_COUNT_ONLY`, mirror mismatches, invalid dates, and unknown outcomes and prove none enter train/holdout.
4. Prove every accepted row is traceable by exact `game_key`.
5. Prove a small but otherwise valid archive remains `NOT_READY`.
6. Search the slice for any code path that emits a probability or treats `READY_FOR_BACKTEST` as permission to publish one.
