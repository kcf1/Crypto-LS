# Data updates

General entry point: **`scripts/run_data_updater.py`** (e.g. Docker `data-updater` service). It runs all registered tasks at a fixed interval.

**One subprocess/task per data source.** Each task module exposes a `run()` function; the wrapper invokes them in order and catches exceptions per task.

## Implemented

- **binance_ohlcv** – Binance OHLCV incremental update with tail refresh (Collector + Storage, delay + 429 retry).

## Adding a new data source

1. Add a module under `data/updates/`, e.g. `data/updates/other_exchange_xyz.py`.
2. Implement a no-arg `run()` function that does one shot of the update (use Collector/Storage, settings, retries as needed).
3. In `data/updates/__init__.py`, import the module and append `("task_name", module.run)` to `TASKS`.

No changes to `run_data_updater.py` or Docker are required.
