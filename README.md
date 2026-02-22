# Benchmarks

This repository hosts benchmark suites for Coi and related ecosystem performance tracking.

## Goals

- Keep benchmark categories isolated by suite
- Support adding new benchmark types beyond framework comparisons
- Standardize execution and result output layout

## Running Benchmarks

```bash
./run.sh                      # Runs default suite: framework
./run.sh framework            # Runs framework suite explicitly
./run.sh framework --dom-only # Pass suite-specific options through
```

## Current Suites

- `framework` — Coi vs React vs Vue vs Svelte bundle and DOM benchmarks

## Repository Structure

```
benchmarks/
├── run.sh                    # Suite orchestrator
└── suites/
	└── framework/
		├── apps/
		│   ├── counter/
		│   │   ├── coi/
		│   │   ├── react/
		│   │   ├── svelte/
		│   │   └── vue/
		│   └── rows/
		│       ├── coi/
		│       ├── react/
		│       ├── svelte/
		│       └── vue/
		├── benchmark.py
		├── results/
		│   ├── benchmark_results.json
		│   └── benchmark_results.svg
		├── README.md
		└── run.sh
```

## Adding a New Benchmark Type

1. Create `suites/<name>/`
2. Add a `run.sh` entry script for that suite
3. Keep suite-specific apps/data under that suite directory
4. Write outputs to `suites/<name>/results/`
5. Document usage in `suites/<name>/README.md`

