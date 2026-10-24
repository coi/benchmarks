#!/usr/bin/env python3
"""
Unified Benchmark Runner for Coi, React, Vue, and Svelte.

Runs two benchmark suites:
1. Bundle Size - Uses counter apps (minimal implementation for clean size comparison)
2. DOM Performance - Uses rows apps (stress test with 1000 rows)
"""

import os
import json
import subprocess
import sys
import asyncio
import statistics

# Check for playwright (only needed for DOM benchmarks)
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

FRAMEWORKS = ['coi', 'react', 'vue', 'svelte']
BENCHMARK_DIR = os.path.dirname(os.path.abspath(__file__))
APPS_DIR = os.path.join(BENCHMARK_DIR, 'apps')
RESULTS_DIR = os.path.join(BENCHMARK_DIR, 'results')

# DOM benchmark operations
DOM_BENCHMARKS = [
    ('create1000', 'Create 1,000 rows'),
    ('clear', 'Clear rows'),
    ('create1000', 'Create 1,000 rows (2nd)'),
    ('update', 'Update 1,000 rows'),
    ('swap', 'Swap rows'),
    ('clear', 'Clear rows (2nd)'),
]

WARMUP_RUNS = 5
BENCHMARK_RUNS = 5
# the frameworks take turns: a cycle opens each one on a fresh page, warms it up and measures,
# and the cycles repeat, so neither the order nor a slow spell of the machine decides a result;
# the number reported is the median of every sample
CYCLES = 3

COLORS = {"coi": "#9477ff", "react": "#00d8ff", "vue": "#42b883", "svelte": "#e97d30"}


def parse_browser(ua: str) -> str:
    """Parse browser name and version from user agent string."""
    if 'Chrome' in ua:
        parts = ua.split('Chrome/')
        if len(parts) > 1:
            ver = parts[1].split(' ')[0]
            return f"Chrome {ver}"
    if 'Firefox' in ua:
        parts = ua.split('Firefox/')
        if len(parts) > 1:
            ver = parts[1].split(' ')[0]
            return f"Firefox {ver}"
    if 'Safari' in ua and 'Version' in ua:
        parts = ua.split('Version/')
        if len(parts) > 1:
            ver = parts[1].split(' ')[0]
            return f"Safari {ver}"
    return "Unknown Browser"


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print('=' * 60)


def build_counter_apps():
    """Build counter apps for bundle size measurement."""
    print("\nBuilding Counter Apps (for bundle size)...")
    
    # Build Coi counter
    coi_dir = os.path.join(APPS_DIR, 'counter', 'coi')
    if os.path.exists(coi_dir):
        try:
            subprocess.check_call(['coi', 'build'], cwd=coi_dir, 
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("  ✓ Coi counter built")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"  ✗ Coi counter failed: {e}")
    
    # Build React, Vue, and Svelte counters
    for fw in ['react', 'vue', 'svelte']:
        fw_dir = os.path.join(APPS_DIR, 'counter', fw)
        if os.path.exists(fw_dir):
            try:
                subprocess.check_call(['npm', 'install'], cwd=fw_dir,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.check_call(['npm', 'run', 'build'], cwd=fw_dir,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"  ✓ {fw.capitalize()} counter built")
            except subprocess.CalledProcessError as e:
                print(f"  ✗ {fw.capitalize()} counter failed: {e}")


def build_rows_apps():
    """Build rows apps for DOM performance measurement."""
    print("\nBuilding Rows Apps (for DOM performance)...")
    
    # Build Coi rows
    coi_dir = os.path.join(APPS_DIR, 'rows', 'coi')
    if os.path.exists(coi_dir):
        try:
            subprocess.check_call(['coi', 'build'], cwd=coi_dir,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("  ✓ Coi rows built")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"  ✗ Coi rows failed: {e}")
    
    # Build React, Vue, and Svelte rows
    for fw in ['react', 'vue', 'svelte']:
        fw_dir = os.path.join(APPS_DIR, 'rows', fw)
        if os.path.exists(fw_dir):
            try:
                subprocess.check_call(['npm', 'install'], cwd=fw_dir,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.check_call(['npm', 'run', 'build'], cwd=fw_dir,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"  ✓ {fw.capitalize()} rows built")
            except subprocess.CalledProcessError as e:
                print(f"  ✗ {fw.capitalize()} rows failed: {e}")


def get_dir_size(path: str) -> int:
    """Get total size of a directory in bytes."""
    total = 0
    if os.path.exists(path):
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total += os.path.getsize(fp)
    return total


def measure_bundle_sizes() -> dict:
    """Measure bundle sizes using counter apps."""
    sizes = {}
    for fw in FRAMEWORKS:
        dist_path = os.path.join(APPS_DIR, 'counter', fw, 'dist')
        sizes[fw] = get_dir_size(dist_path)
    return sizes


async def click_settled(page, button_id: str):
    """A click and the frame after it, nothing timed: warm-ups and the steps between measurements."""
    await page.evaluate(r'''(buttonId) => new Promise((resolve) => {
        document.getElementById(buttonId).click();
        requestAnimationFrame(() => requestAnimationFrame(resolve));
    })''', button_id)


async def run_dom_benchmark(browser, page, button_id: str) -> float:
    """One operation, timed from a trace: the click's dispatch to the end of the frame's commit.

    A clock around the click and a double requestAnimationFrame would wait for the next vsync,
    so an operation of 2 ms could read 2 or 15 depending on where in the frame it landed. The
    trace has the browser's own account: the click's EventDispatch, then the main-thread frame
    that paints the change, which ends with its Commit to the compositor."""
    await browser.start_tracing(page=page, categories=['devtools.timeline', 'disabled-by-default-devtools.timeline'])
    await click_settled(page, button_id)
    events = json.loads(await browser.stop_tracing())['traceEvents']
    clicks = [e for e in events if e.get('name') == 'EventDispatch' and (e.get('args') or {}).get('data', {}).get('type') == 'click']
    if not clicks:
        return -1
    start = min(e['ts'] for e in clicks)
    after = sorted((e for e in events if e.get('ph') == 'X' and e['ts'] >= start), key=lambda e: e['ts'])
    commit = next((e for e in after if e['name'] == 'Commit'), None)
    if commit:
        end = commit['ts'] + commit['dur']
    else:
        paints = [e['ts'] + e['dur'] for e in after if e['name'] == 'Paint']
        if not paints:
            return -1
        end = max(paints)
    return (end - start) / 1000.0

def summarize(samples: dict) -> dict:
    """{label: [durations]} -> {label: {median, mean, min, max, stddev, samples}}."""
    out = {}
    for label, durations in samples.items():
        if durations:
            out[label] = {
                'median': statistics.median(durations),
                'mean': statistics.mean(durations),
                'min': min(durations),
                'max': max(durations),
                'stddev': statistics.stdev(durations) if len(durations) > 1 else 0,
                'samples': len(durations),
            }
        else:
            out[label] = {'median': -1, 'mean': -1, 'error': 'No valid results'}
    return out


async def benchmark_framework_dom(browser, framework: str, port: int) -> dict:
    """One cycle of the DOM benchmarks for a framework: {label: [durations]}."""
    results = {}
    page = await browser.new_page()
    await page.goto(f'http://localhost:{port}')
    await page.wait_for_selector('.controls')
    
    # Wait 2 seconds for page to fully load and stabilize
    print(f"      Waiting 2s for page to stabilize...", flush=True)
    await asyncio.sleep(2.0)
    
    # Warmup runs - give JIT time to optimize
    for _ in range(WARMUP_RUNS):
        await click_settled(page, 'create1000')
        await asyncio.sleep(0.1)
        await click_settled(page, 'clear')
        await asyncio.sleep(0.1)

    # Run benchmarks
    for button_id, label in DOM_BENCHMARKS:
        durations = []
        for _ in range(BENCHMARK_RUNS):
            # Clear before each create to ensure consistent starting state
            if button_id == 'create1000':
                await click_settled(page, 'clear')
                await asyncio.sleep(0.05)
            duration = await run_dom_benchmark(browser, page, button_id)
            if duration > 0:
                durations.append(duration)
            await asyncio.sleep(0.05)
        
        results[label] = durations

    await page.close()
    return results


async def run_dom_benchmarks() -> tuple:
    """Run DOM performance benchmarks using rows apps."""
    if not PLAYWRIGHT_AVAILABLE:
        print("  ⚠ Playwright not available, skipping DOM benchmarks")
        print("    Install with: pip install playwright && playwright install chromium")
        return {}, ""
    
    all_results = {}
    servers = {}
    
    # Start servers
    print("\n  Starting servers...")
    base_port = 5173
    for i, fw in enumerate(FRAMEWORKS):
        port = base_port + i
        fw_dir = os.path.join(APPS_DIR, 'rows', fw, 'dist')
        
        if not os.path.exists(fw_dir):
            print(f"    ✗ {fw.capitalize()} dist not found")
            continue
        
        process = subprocess.Popen(
            [sys.executable, '-m', 'http.server', str(port)],
            cwd=fw_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        servers[fw] = {'process': process, 'port': port}
        print(f"    ✓ {fw.capitalize()} on port {port}")
    
    await asyncio.sleep(2)
    
    # Run benchmarks
    print("\n  Running benchmarks...")
    print("  Waiting 2 seconds for everything to be ready...", flush=True)
    await asyncio.sleep(2)
    
    browser_name = "Unknown Browser"
    async with async_playwright() as p:
        # Use visible browser - headless throttles requestAnimationFrame
        browser = await p.chromium.launch(headless=False)
        
        samples = {fw: {} for fw in FRAMEWORKS}
        failed = {}
        for cycle in range(CYCLES):
            print(f"  Cycle {cycle + 1} of {CYCLES}")
            for fw in FRAMEWORKS:
                if fw not in servers or fw in failed:
                    continue

                port = servers[fw]['port']
                print(f"    {fw.capitalize()} (port {port})...", flush=True)
                try:
                    if browser_name == "Unknown Browser":
                        page = await browser.new_page()
                        await page.goto(f'http://localhost:{port}')
                        browser_name = parse_browser(await page.evaluate('navigator.userAgent'))
                        print(f"  Browser: {browser_name}")
                        await page.close()
                    results = await benchmark_framework_dom(browser, fw, port)
                    for label, durations in results.items():
                        samples[fw].setdefault(label, []).extend(durations)
                    create_time = statistics.median(results.get('Create 1,000 rows') or [-1])
                    print(f"      -> Create 1000: {create_time:.1f}ms ✓")
                except Exception as e:
                    print(f"      ✗ ({e})")
                    failed[fw] = str(e)

        for fw in FRAMEWORKS:
            if fw in failed:
                all_results[fw] = {'error': failed[fw]}
            elif samples[fw]:
                all_results[fw] = summarize(samples[fw])

        await browser.close()
    
    # Stop servers
    for fw, server in servers.items():
        server['process'].terminate()
    
    return all_results, browser_name


# ---- ranking and the shown values ---------------------------------------------------------
# a value is judged as it is printed, to one decimal: two frameworks that print the same number
# are tied, both get the star, and tied names come in alphabetical order

def shown(v: float) -> float:
    return round(v + 1e-9, 1)


def ranked(vals):
    """[(fw, value)] -> (sorted by shown value then name, the shown best, the raw best)."""
    order = sorted(vals, key=lambda x: (shown(x[1]), x[0]))
    if not order:
        return [], None, None
    best = shown(order[0][1])
    best_raw = min(v for _, v in order if shown(v) == best)
    return order, best, best_raw


def is_best(v, best) -> bool:
    return best is not None and shown(v) == best


def pct_more(v, best, best_raw, floor=0.5) -> str:
    """how far behind the best, as printed next to a value: '+34%'; nothing for the best, or when
    the gap is under floor (half a millisecond, a kilobyte): a percentage of a tenth is noise."""
    if is_best(v, best) or not best_raw or v - best_raw < floor:
        return ''
    return f'+{(v / best_raw - 1) * 100:.0f}%'


def print_bundle_results(sizes: dict):
    """Print bundle size results."""
    print_header("BUNDLE SIZE (Counter App)")
    print(f"{'Framework':<12} | {'Size':>10} | {'vs best':>8}")
    print("-" * 36)
    order, best, best_raw = ranked([(fw, s / 1024) for fw, s in sizes.items() if s > 0])
    for fw, kb in order:
        name = fw.capitalize() + (" ★" if is_best(kb, best) else "")
        print(f"{name:<12} | {kb:>7.1f} KB | {pct_more(kb, best, best_raw, 1.0):>8}")


def print_dom_results(results: dict):
    """Print DOM benchmark results."""
    if not results:
        return

    print_header("DOM PERFORMANCE (Rows App)")
    benchmarks = ['Create 1,000 rows', 'Update 1,000 rows', 'Swap rows', 'Clear rows']
    header = f"{'Benchmark':<20}"
    for fw in FRAMEWORKS:
        header += f" | {fw.capitalize():>15}"
    print(header)
    print("-" * len(header))
    for bench in benchmarks:
        vals = [(fw, results[fw][bench]['median']) for fw in FRAMEWORKS
                if fw in results and bench in results[fw] and results[fw][bench].get('median', -1) > 0]
        _, best, best_raw = ranked(vals)
        row = f"{bench:<20}"
        for fw in FRAMEWORKS:
            v = dict(vals).get(fw)
            if v is None:
                row += f" | {'n/a':>15}"
                continue
            cell = f"{v:.1f}ms" + (" ★" if is_best(v, best) else f" {pct_more(v, best, best_raw)}")
            row += f" | {cell:>15}"
        print(row)
    print("-" * len(header))


# ---- the chart -----------------------------------------------------------------------------

def framework_marks() -> str:
    """<symbol>s for the four marks: the koi from the repository's logo, an atom, the V, an S."""
    paths = ''
    logo = os.path.join(BENCHMARK_DIR, '..', '..', 'images', 'logo.svg')
    if os.path.exists(logo):
        import re
        with open(logo) as f:
            # the koi is the logo's paths; its rects are a small bar chart of their own
            paths = ''.join(re.findall(r'<path [^>]*/>', f.read()))
    marks = [
        f'<symbol id="m-coi" viewBox="15 0 163 108">{paths}</symbol>',
        '<symbol id="m-react" viewBox="0 0 24 24"><circle cx="12" cy="12" r="2.3" fill="#00d8ff"/>'
        + ''.join(f'<ellipse cx="12" cy="12" rx="10.5" ry="4" fill="none" stroke="#00d8ff" stroke-width="1.3" transform="rotate({a} 12 12)"/>' for a in (0, 60, 120))
        + '</symbol>',
        '<symbol id="m-vue" viewBox="0 0 24 24"><path d="M2 3h4l6 10.4L18 3h4L12 21z" fill="#42b883"/><path d="M6.6 3h3l2.4 4.2L14.4 3h3l-5.4 9.4z" fill="#35495e"/></symbol>',
        '<symbol id="m-svelte" viewBox="0 0 24 24"><path d="M17 6.2c-2.4-2.3-6.4-2.6-8.8-.6-2.3 1.9-1.8 5 .8 6.2 2.6 1.2 6.4 1 7.5 3.7 1.1 2.6-1.3 5.3-4.3 5.6-2.6.3-4.9-.6-6.3-2.3" fill="none" stroke="#e97d30" stroke-width="3.2" stroke-linecap="round"/></symbol>',
    ]
    return '<defs>' + ''.join(marks) + '</defs>'


def mark(fw: str, x: float, y: float, size: float) -> str:
    return f'<use href="#m-{fw}" x="{x:.1f}" y="{y:.1f}" width="{size * 1.6:.1f}" height="{size}"/>'


def generate_svg_report(bundle_sizes: dict, dom_results: dict, browser_name: str = "", date: str = ""):
    """The chart: bundle sizes, the DOM operations, Coi against the best of the others."""
    has_dom = bool(dom_results)
    width = 820
    bg, text_main, text_sub, line = "#fbfbfd", "#1f2328", "#6b7280", "#e5e7eb"
    green, orange = "#16a34a", "#d97706"
    body = []
    font = "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;"

    # the title, what ran it and when, the legend
    body.append(f'<text x="{width/2}" y="38" text-anchor="middle" fill="{text_main}" font-size="22" font-weight="bold">Coi vs React vs Vue vs Svelte</text>')
    sub = " · ".join(s for s in (browser_name, date) if s)
    if sub:
        body.append(f'<text x="{width/2}" y="57" text-anchor="middle" fill="{text_sub}" font-size="12">{sub}</text>')
    legend_x = width / 2 - 190
    for i, fw in enumerate(FRAMEWORKS):
        lx = legend_x + i * 100
        body.append(mark(fw, lx, 70, 16))
        body.append(f'<text x="{lx + 32}" y="83" fill="{text_main}" font-size="13" font-weight="600">{fw.capitalize()}</text>')

    y = 128
    chart_x = 190
    max_bar_width = 400

    def label(x, yy, value, best, best_raw, unit, size, floor=0.5):
        star = " ★" if is_best(value, best) else ""
        weight = "bold" if star else "normal"
        more = pct_more(value, best, best_raw, floor)
        out = [f'<text x="{x:.1f}" y="{yy}" fill="{text_main}" font-size="{size}" font-weight="{weight}">{value:.1f} {unit}{star}</text>']
        if more:
            out.append(f'<text x="{x + (len(f"{value:.1f} {unit}") * size * 0.58):.1f}" y="{yy}" fill="{text_sub}" font-size="{size - 1}">{more}</text>')
        return out

    # bundle sizes
    body.append(f'<text x="{width/2}" y="{y}" text-anchor="middle" fill="{text_main}" font-size="16" font-weight="bold">Bundle size</text>')
    body.append(f'<text x="{width/2}" y="{y + 18}" text-anchor="middle" fill="{text_sub}" font-size="12">Counter app, everything served · smaller is better</text>')
    y += 42
    order, best, best_raw = ranked([(fw, s / 1024) for fw, s in bundle_sizes.items() if s > 0])
    max_size = max((kb for _, kb in order), default=1)
    for fw, kb in order:
        bar_w = max(2, kb / max_size * max_bar_width)
        body.append(mark(fw, chart_x - 128, y + 4, 18))
        body.append(f'<text x="{chart_x - 14}" y="{y + 18}" text-anchor="end" fill="{text_main}" font-size="13" font-weight="600">{fw.capitalize()}</text>')
        body.append(f'<rect x="{chart_x}" y="{y}" width="{bar_w:.1f}" height="26" fill="{COLORS[fw]}" rx="4"/>')
        body.extend(label(chart_x + bar_w + 10, y + 18, kb, best, best_raw, "KB", 13, 1.0))
        y += 36

    if has_dom:
        y += 24
        body.append(f'<text x="{width/2}" y="{y}" text-anchor="middle" fill="{text_main}" font-size="16" font-weight="bold">DOM performance</text>')
        body.append(f'<text x="{width/2}" y="{y + 18}" text-anchor="middle" fill="{text_sub}" font-size="12">Rows app, 1,000 rows, median of {BENCHMARK_RUNS * CYCLES} · lower is better</text>')
        y += 42
        benchmarks = ['Create 1,000 rows', 'Update 1,000 rows', 'Swap rows', 'Clear rows']
        max_val = max((dom_results[fw][b]['median'] for fw in FRAMEWORKS for b in benchmarks
                       if fw in dom_results and b in dom_results[fw] and dom_results[fw][b].get('median', 0) > 0), default=1)
        bar_h, bar_gap, group_gap = 18, 4, 26
        for bench in benchmarks:
            vals = [(fw, dom_results[fw][bench]['median']) for fw in FRAMEWORKS
                    if fw in dom_results and bench in dom_results[fw] and dom_results[fw][bench].get('median', -1) > 0]
            order, best, best_raw = ranked(vals)
            body.append(f'<text x="{chart_x - 128}" y="{y + 4}" fill="{text_main}" font-size="12" font-weight="bold">{bench}</text>')
            bar_y = y + 14
            for fw, v in order:
                bar_w = max(2, v / max_val * max_bar_width)
                body.append(mark(fw, chart_x - 128, bar_y + 2, 14))
                body.append(f'<text x="{chart_x - 100}" y="{bar_y + 13}" fill="{text_sub}" font-size="11">{fw.capitalize()}</text>')
                body.append(f'<rect x="{chart_x}" y="{bar_y}" width="{bar_w:.1f}" height="{bar_h}" fill="{COLORS[fw]}" rx="3"/>')
                body.extend(label(chart_x + bar_w + 8, bar_y + 13, v, best, best_raw, "ms", 11))
                bar_y += bar_h + bar_gap
            y = bar_y + group_gap

        # Coi against the best of the others
        y += 6
        body.append(f'<text x="{width/2}" y="{y}" text-anchor="middle" fill="{text_main}" font-size="14" font-weight="bold">Coi against the best of the others</text>')
        y += 26
        col_metric, col_coi, col_other, col_diff = 110, 330, 520, 710
        for x, t, anchor, color in ((col_metric, "Metric", "start", text_sub), (col_coi, "Coi", "end", COLORS["coi"]),
                                    (col_other, "Best other", "end", text_sub), (col_diff, "Difference", "end", text_sub)):
            body.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}" font-size="11" font-weight="bold">{t}</text>')
        y += 8
        body.append(f'<line x1="{col_metric}" y1="{y}" x2="{col_diff}" y2="{y}" stroke="{line}"/>')
        y += 16

        rows = []
        if bundle_sizes.get('coi'):
            others = [(fw, s / 1024) for fw, s in bundle_sizes.items() if fw != 'coi' and s > 0]
            if others:
                fw, v = min(others, key=lambda x: (shown(x[1]), x[0]))
                rows.append(('Bundle size', bundle_sizes['coi'] / 1024, v, fw, 'KB'))
        for bench in benchmarks:
            if 'coi' in dom_results and bench in dom_results['coi']:
                others = [(fw, dom_results[fw][bench]['median']) for fw in FRAMEWORKS
                          if fw != 'coi' and fw in dom_results and bench in dom_results[fw] and dom_results[fw][bench].get('median', 0) > 0]
                if others:
                    fw, v = min(others, key=lambda x: (shown(x[1]), x[0]))
                    rows.append((bench, dom_results['coi'][bench]['median'], v, fw, 'ms'))
        for metric, coi_v, other_v, other_fw, unit in rows:
            if shown(coi_v) == shown(other_v) or abs(coi_v - other_v) < (1.0 if unit == 'KB' else 0.5):
                diff, color = "same", text_sub
            else:
                pct = (coi_v / other_v - 1) * 100 if other_v else 0
                word = "less" if coi_v < other_v else "more"
                diff = f'{pct:+.0f}% ({abs(coi_v - other_v):.1f} {unit} {word})'
                color = green if coi_v < other_v else orange
            body.append(f'<text x="{col_metric}" y="{y}" fill="{text_main}" font-size="11">{metric}</text>')
            body.append(f'<text x="{col_coi}" y="{y}" text-anchor="end" fill="{text_main}" font-size="11" font-weight="{"bold" if coi_v <= other_v else "normal"}">{coi_v:.1f} {unit}</text>')
            body.append(f'<text x="{col_other}" y="{y}" text-anchor="end" fill="{text_sub}" font-size="11">{other_v:.1f} {unit} ({other_fw.capitalize()})</text>')
            body.append(f'<text x="{col_diff}" y="{y}" text-anchor="end" fill="{color}" font-size="11" font-weight="bold">{diff}</text>')
            y += 18

    height = y + 16
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" style="{font} background: {bg};">',
           framework_marks(),
           f'<rect width="100%" height="100%" fill="{bg}"/>'] + body + ['</svg>']

    os.makedirs(RESULTS_DIR, exist_ok=True)
    output_path = os.path.join(RESULTS_DIR, 'benchmark_results.svg')
    with open(output_path, 'w') as f:
        f.write('\n'.join(svg))
    print(f"\n✓ SVG report: {output_path}")


def main():
    skip_build = "--no-build" in sys.argv
    size_only = "--size-only" in sys.argv
    dom_only = "--dom-only" in sys.argv
    json_path = os.path.join(RESULTS_DIR, 'benchmark_results.json')

    # the tables and the chart again from the last run's results, nothing measured
    if "--report-only" in sys.argv:
        with open(json_path) as f:
            saved = json.load(f)
        print_bundle_results(saved.get('bundle_sizes', {}))
        print_dom_results(saved.get('dom_performance', {}))
        generate_svg_report(saved.get('bundle_sizes', {}), saved.get('dom_performance', {}), saved.get('browser', ''), saved.get('date', ''))
        return

    print_header("COI BENCHMARK SUITE")

    # Build projects
    if not skip_build:
        if not dom_only:
            build_counter_apps()
        if not size_only:
            build_rows_apps()

    # Measure bundle sizes
    bundle_sizes = {}
    if not dom_only:
        bundle_sizes = measure_bundle_sizes()
        print_bundle_results(bundle_sizes)

    # Run DOM benchmarks
    dom_results = {}
    browser_name = ""
    if not size_only:
        print_header("RUNNING DOM BENCHMARKS")
        dom_results, browser_name = asyncio.run(run_dom_benchmarks())
        print_dom_results(dom_results)

    import datetime
    date = datetime.date.today().isoformat()
    generate_svg_report(bundle_sizes, dom_results, browser_name, date)

    output = {
        'browser': browser_name,
        'date': date,
        'bundle_sizes': bundle_sizes,
        'dom_performance': dom_results
    }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(json_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"✓ JSON results: {json_path}")


if __name__ == "__main__":
    main()
