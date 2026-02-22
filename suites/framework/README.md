# Framework Benchmark Suite

This suite compares **Coi**, **React**, **Vue**, and **Svelte**.

## What's Measured

| Benchmark | Apps Used | Measures |
|-----------|-----------|----------|
| **Bundle Size** | `apps/counter/*` | Total production build size (HTML + JS + CSS + WASM) |
| **DOM Performance** | `apps/rows/*` | Create, update, swap, and clear 1,000 rows |

## Prerequisites

- **Python 3**: For the benchmark runner
- **Node.js & npm**: Required to build React, Vue, and Svelte apps
- **Coi**: The `coi` command must be in PATH
- **Playwright** (optional): For DOM benchmarks (`pip install playwright && playwright install chromium`)

## Run

From the repository root:

```bash
./run.sh framework
```

Or from this suite directory:

```bash
./run.sh
```

### Options

```bash
./run.sh --no-build    # Skip building, use existing dist folders
./run.sh --size-only   # Only measure bundle sizes
./run.sh --dom-only    # Only run DOM performance benchmarks
```

## Results

Generated in `results/`:

- `benchmark_results.json` — Raw data
- `benchmark_results.svg` — Visual comparison chart

![Benchmark Results](results/benchmark_results.svg)
