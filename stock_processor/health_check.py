#!/usr/bin/env python3
"""
Code health check for Stock Transaction Processor.

Runs on every git commit (via pre-commit hook). All checks must pass.

Usage:
  python health_check.py              # run all checks
  python health_check.py --static     # skip regression tests (static checks only)
  python health_check.py --baseline   # record current counts as the new baseline

Checks:
  1. Regression tests — all must pass (hard block)
  2. Duplicate utility functions — same helper in 3+ broker files (hard block)
  3. Long functions — count cannot INCREASE from baseline (ratchet)
  4. sys.path hacks — count cannot INCREASE from baseline (ratchet)
"""
import ast
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
MAX_FUNC_LOC = 40
MIN_DUP_FILES = 3  # flag if same function name appears in this many broker files

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BROKERS_DIR = os.path.join(_SCRIPT_DIR, 'brokers')
_BASELINE_FILE = os.path.join(_SCRIPT_DIR, '.health_baseline.json')

# Files to scan for static checks
_SCAN_DIRS = [_SCRIPT_DIR, _BROKERS_DIR]
_SKIP_FILES = {'__pycache__', '.pyc'}

# Intentional interface names — every broker defines these by design.
# Only flag utility helpers that are actual copy-paste duplicates.
_INTERFACE_NAMES = {
    'process',          # standard broker entry point
    '_process_sheet',   # standard per-sheet processor
    '_classify_row',    # standard row classifier
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _py_files(dirs):
    """Yield (filepath, relative_name) for .py files."""
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith('.py') and fname not in _SKIP_FILES:
                fpath = os.path.join(d, fname)
                rel = os.path.relpath(fpath, _SCRIPT_DIR)
                yield fpath, rel


def _get_functions(filepath):
    """Parse a Python file, return list of (name, start, end, loc)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
    except (SyntaxError, UnicodeDecodeError):
        return []

    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = max(getattr(node, 'end_lineno', start), start)
            funcs.append((node.name, start, end, end - start + 1))
    return funcs


def _load_baseline():
    """Load baseline counts. Returns dict or None."""
    if os.path.exists(_BASELINE_FILE):
        with open(_BASELINE_FILE, 'r') as f:
            return json.load(f)
    return None


def _save_baseline(data):
    with open(_BASELINE_FILE, 'w') as f:
        json.dump(data, f, indent=2)


# ── Check 1: Regression tests ────────────────────────────────────────────────
def check_regression():
    """Run test_regression.py. Hard block on failure."""
    test_script = os.path.join(_SCRIPT_DIR, 'test_regression.py')
    if not os.path.exists(test_script):
        return False, ['  test_regression.py not found']

    result = subprocess.run(
        [sys.executable, test_script],
        capture_output=True, text=True,
        cwd=_SCRIPT_DIR, timeout=120,
    )

    if result.returncode == 0:
        lines = result.stdout.strip().splitlines()
        summary = next(
            (l for l in lines if 'passed' in l),
            lines[-1] if lines else '',
        )
        return True, [f'  {summary.strip()}']

    msgs = []
    for line in result.stdout.splitlines():
        if line.startswith('FAIL') or line.startswith('  '):
            msgs.append(f'  {line}')
    if result.stderr:
        msgs.append(f'  STDERR: {result.stderr[:200]}')
    return False, msgs


# ── Check 2: Duplicate utility functions ──────────────────────────────────────
def check_duplicates():
    """Flag utility helpers duplicated in 3+ broker files. Hard block."""
    func_files = defaultdict(set)

    for fpath, rel in _py_files([_BROKERS_DIR]):
        for func_name, _, _, _ in _get_functions(fpath):
            if func_name not in _INTERFACE_NAMES:
                func_files[func_name].add(rel)

    issues = []
    for func_name, files in sorted(func_files.items()):
        if len(files) >= MIN_DUP_FILES:
            issues.append(
                f'  {func_name}() — in {len(files)} files: '
                f'{", ".join(sorted(files))}'
            )

    return len(issues) == 0, issues


# ── Check 3: Long functions (ratchet) ────────────────────────────────────────
def count_long_functions():
    """Return list of long function descriptions."""
    issues = []
    for fpath, rel in _py_files(_SCAN_DIRS):
        for func_name, start, end, loc in _get_functions(fpath):
            if loc > MAX_FUNC_LOC:
                issues.append(
                    f'  {rel}:{start} — {func_name}() '
                    f'is {loc} lines (max {MAX_FUNC_LOC})'
                )
    return issues


def check_long_functions(baseline):
    """Ratchet: fail if count increased from baseline."""
    issues = count_long_functions()
    current = len(issues)
    limit = baseline.get('long_functions', current) if baseline else current

    if current > limit:
        msgs = [f'  Count increased: {current} (was {limit})'] + issues
        return False, msgs, current

    status_msg = f'  {current} long functions (baseline: {limit})'
    if current < limit:
        status_msg += f' — improved by {limit - current}!'
    return True, [status_msg], current


# ── Check 4: sys.path hacks (ratchet) ────────────────────────────────────────
def count_sys_path_hacks():
    """Return list of sys.path hack descriptions."""
    pattern = re.compile(r'sys\.path\.(insert|append)\(')
    issues = []
    for fpath, rel in _py_files(_SCAN_DIRS):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                for lineno, line in enumerate(f, 1):
                    if pattern.search(line):
                        issues.append(f'  {rel}:{lineno} — {line.strip()}')
        except (UnicodeDecodeError, OSError):
            pass
    return issues


def check_sys_path_hacks(baseline):
    """Ratchet: fail if count increased from baseline."""
    issues = count_sys_path_hacks()
    current = len(issues)
    limit = baseline.get('sys_path_hacks', current) if baseline else current

    if current > limit:
        msgs = [f'  Count increased: {current} (was {limit})'] + issues
        return False, msgs, current

    status_msg = f'  {current} sys.path hacks (baseline: {limit})'
    if current < limit:
        status_msg += f' — improved by {limit - current}!'
    return True, [status_msg], current


# ── Runner ────────────────────────────────────────────────────────────────────
def _print_check(passed, label, msgs):
    print(f'[{"PASS" if passed else "FAIL"}]  {label}')
    for m in msgs:
        print(m)
    return passed


def _run_hard_checks(static_only):
    all_passed = True
    if not static_only:
        passed, msgs = check_regression()
        if not _print_check(passed, 'Regression tests', msgs):
            all_passed = False
    passed, msgs = check_duplicates()
    if not _print_check(passed, 'Duplicate utility functions', msgs):
        all_passed = False
    return all_passed


def _run_ratchet_checks(baseline):
    all_passed = True
    new_baseline = {}

    passed, msgs, count = check_long_functions(baseline)
    if not _print_check(passed, f'Long functions (>{MAX_FUNC_LOC} LOC)', msgs):
        all_passed = False
    new_baseline['long_functions'] = count

    passed, msgs, count = check_sys_path_hacks(baseline)
    if not _print_check(passed, 'sys.path hacks', msgs):
        all_passed = False
    new_baseline['sys_path_hacks'] = count

    return all_passed, new_baseline


def _auto_update_baseline(baseline, new_baseline):
    if not baseline:
        return
    improved = any(
        new_baseline[key] < baseline.get(key, new_baseline[key])
        for key in new_baseline
    )
    if improved:
        _save_baseline(new_baseline)
        print('\n  Baseline auto-updated (counts improved)')


def main():
    args = sys.argv[1:]
    static_only = '--static' in args
    update_baseline = '--baseline' in args

    if update_baseline:
        data = {
            'long_functions': len(count_long_functions()),
            'sys_path_hacks': len(count_sys_path_hacks()),
        }
        _save_baseline(data)
        print(f'Baseline saved: {data}')
        return

    baseline = _load_baseline()

    print(f'\n{"="*50}')
    print('HEALTH CHECK')
    print(f'{"="*50}\n')

    hard_ok = _run_hard_checks(static_only)
    ratchet_ok, new_baseline = _run_ratchet_checks(baseline)
    all_passed = hard_ok and ratchet_ok

    if all_passed:
        _auto_update_baseline(baseline, new_baseline)

    print(f'\n{"="*50}')
    print('ALL CHECKS PASSED' if all_passed else 'HEALTH CHECK FAILED — commit blocked')
    print(f'{"="*50}\n')

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
