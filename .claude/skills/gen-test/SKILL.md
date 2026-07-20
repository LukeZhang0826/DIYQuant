---
name: gen-test
description: Write pytest tests for a diyquant module following the repo's existing test patterns. Use when asked to add or generate tests.
---

# gen-test

Write tests for the module the user names (e.g. `/gen-test signals/technical/sma_crossover.py`).

## Repo test conventions (follow exactly)

- Tests live flat in `tests/`, named `test_<module>.py` (e.g. `tests/test_sma_crossover.py`).
- Plain pytest functions, no test classes. `pytest.raises` for validation errors.
- Synthetic market data via small builder helpers defined at the top of the test file, e.g.:

```python
def make_bars(prices: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.DataFrame({"close": prices}, index=idx)
```

- Deterministic inputs (`np.linspace` ramps, fixed date ranges): no random data, no network calls, no yfinance in tests.
- Import from the installed package: `from diyquant.signals... import ...` (src layout; the package is installed editable).
- Each test asserts one behavior with a descriptive name (`test_warmup_is_flat`, `test_fast_must_be_less_than_slow`).

## Workflow

1. Read the target module and its existing test file if one exists.
2. Cover: happy path per public method, boundary/warmup behavior, and constructor/input validation.
3. Run `python -m pytest tests/test_<module>.py -q` and iterate until green.
