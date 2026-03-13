"""
Math 24/60 Puzzle Library Generator
====================================
Exhaustively finds all solvable 4-number combinations for each difficulty tier,
computes fun/quality scores, and outputs per-tier JSON files.

Output files:
  puzzles_easy.json      1-9,  target 24
  puzzles_medium.json    1-19, target 24
  puzzles_hard.json      1-29, target 24
  puzzles_expert.json    1-49, target 24
  puzzles_extreme.json   1-49, target 24  (capped at 1-49 as agreed)
  puzzles_fraction.json  1-9,  target 24, fraction-only puzzles
  puzzles_t60_easy.json  ... same tiers but target=60
  ... etc

Each puzzle entry:
  {
    "n": [a, b, c, d],
    "s": ["expr1", "expr2", "expr3"],  # up to 3 solutions
    "c": <total solution count>,
    "q": <quality score 0-100>,
    "f": <true if requires intermediate fraction>
  }

Usage:
  python generate_puzzles.py

Estimated runtime: 5-15 minutes depending on machine.
"""

import itertools
import json
import math
import os
import time
from fractions import Fraction

# ── Config ────────────────────────────────────────────────────────────────────

TIERS = [
    ("easy",    range(1, 10)),   # 1-9
    ("medium",  range(1, 20)),   # 1-19
    ("hard",    range(1, 30)),   # 1-29
    ("expert",  range(1, 50)),   # 1-49
    ("extreme", range(1, 50)),   # 1-49 (capped as agreed)
]

TARGETS = [24, 60]

MAX_SOLUTIONS_STORED = 3

# ── Expression Engine (using Fraction for exact arithmetic) ───────────────────

OPS = ['+', '-', '*', '/']

def apply_op(a, b, op):
    """Apply op to Fractions a and b. Returns Fraction or None on invalid."""
    if op == '+': return a + b
    if op == '-': return a - b
    if op == '*': return a * b
    if op == '/':
        if b == 0: return None
        return a / b

def all_results(nums):
    """
    Yield (value, expr_string, uses_fraction) for every distinct expression
    tree over the list of Fraction nums.
    Uses recursive splitting into left/right subsets.
    """
    n = len(nums)
    if n == 1:
        v = nums[0]
        s = str(int(v)) if v.denominator == 1 else str(v)
        yield (v, s, False)
        return

    indices = list(range(n))
    for size in range(1, n):
        for left_idx in itertools.combinations(indices, size):
            right_idx = tuple(i for i in indices if i not in left_idx)
            left_nums  = [nums[i] for i in left_idx]
            right_nums = [nums[i] for i in right_idx]

            for lv, ls, lf in all_results(left_nums):
                for rv, rs, rf in all_results(right_nums):
                    for op in OPS:
                        result = apply_op(lv, rv, op)
                        if result is None:
                            continue
                        # detect intermediate fraction
                        uses_frac = lf or rf or (result.denominator != 1)
                        op_sym = {'+':('+'), '-':('−'), '*':('×'), '/':('÷')}[op]
                        # parenthesise sub-expressions for clarity
                        ls_p = f"({ls})" if any(c in ls for c in '+-−×÷') and size > 1 else ls
                        rs_p = f"({rs})" if any(c in rs for c in '+-−×÷') and n - size > 1 else rs
                        expr = f"{ls_p}{op_sym}{rs_p}"
                        yield (result, expr, uses_frac)


def solve(numbers, target):
    """
    Return list of unique solution strings for the given numbers and target.
    Numbers is a list of ints; target is int.
    Returns (solutions_list, any_requires_fraction)
    """
    target_frac = Fraction(target)
    fracs = [Fraction(n) for n in numbers]

    seen_exprs = set()
    solutions = []
    any_frac = False

    for perm in itertools.permutations(fracs):
        for val, expr, uses_frac in all_results(list(perm)):
            if val == target_frac:
                # Normalise whitespace for dedup
                key = expr.replace(' ', '')
                if key not in seen_exprs:
                    seen_exprs.add(key)
                    solutions.append((expr, uses_frac))
                    if uses_frac:
                        any_frac = True

    return solutions, any_frac


# ── Fun / Quality Score ────────────────────────────────────────────────────────

def quality_score(numbers, solutions, target, requires_fraction):
    """
    Returns integer quality score 0-100.

    Components:
      - Target-in-set penalty      : -40 if target in numbers (trivial shortcut)
      - Solution count score       : 0-25 (sweet spot 2-8)
      - Operator variety score     : 0-20 (best soln uses - or ÷)
      - Multiplicative identity    : 0 to -10 (mild: ×1 or +0 abuse)
      - Number spread              : 0-20 (std dev of numbers)
      - Repetition penalty         : 0 to -15
      - Meaningful use score       : 0-15 (all nums change result)
    """
    score = 50  # base

    # 1. Target in set
    if target in numbers:
        score -= 40

    # 2. Solution count — sweet spot 2-8
    c = len(solutions)
    if c == 0:
        return 0
    elif c == 1:
        sol_score = 10
    elif c <= 8:
        sol_score = 25
    elif c <= 15:
        sol_score = 15
    elif c <= 30:
        sol_score = 8
    else:
        sol_score = 2
    score += sol_score - 15  # -15 because we start with base contribution

    # 3. Operator variety — check best solutions
    has_minus = False
    has_divide = False
    for expr, _ in solutions[:5]:
        if '−' in expr: has_minus = True
        if '÷' in expr: has_divide = True
    op_score = 0
    if has_minus:  op_score += 10
    if has_divide: op_score += 10
    score += op_score

    # 4. Multiplicative identity abuse (×1 or n+0)
    ones = numbers.count(1)
    zeros = numbers.count(0)
    identity_penalty = min(10, ones * 4 + zeros * 5)
    score -= identity_penalty

    # 5. Number spread (std dev)
    mean = sum(numbers) / 4
    variance = sum((x - mean) ** 2 for x in numbers) / 4
    std = math.sqrt(variance)
    spread_score = min(20, int(std * 1.5))
    score += spread_score

    # 6. Repetition penalty
    from collections import Counter
    counts = Counter(numbers)
    max_rep = max(counts.values())
    if max_rep == 4:
        rep_penalty = 15
    elif max_rep == 3:
        rep_penalty = 10
    elif max_rep == 2:
        rep_penalty = 4
    else:
        rep_penalty = 0
    score -= rep_penalty

    # 7. Meaningful use — check if any solution uses a number trivially
    # Proxy: does a solution contain ×1 literally?
    trivial_use = any('×1' in e or '1×' in e or '+0' in e or '0+' in e
                      for e, _ in solutions[:3])
    if not trivial_use:
        score += 15

    return max(0, min(100, score))


# ── Combination Generator ─────────────────────────────────────────────────────

def combos_with_repetition(rng):
    """All 4-element multisets from range (combinations with repetition)."""
    return list(itertools.combinations_with_replacement(rng, 4))


# ── Main Generation ───────────────────────────────────────────────────────────

def generate_tier(tier_name, num_range, target, fraction_only=False):
    combos = combos_with_repetition(num_range)
    total = len(combos)
    puzzles = []
    t0 = time.time()

    print(f"\n  {tier_name} | target={target} | {total} combos to check...")

    for i, nums in enumerate(combos):
        nums_list = list(nums)
        solutions, requires_frac = solve(nums_list, target)

        if not solutions:
            continue

        if fraction_only and not requires_frac:
            continue

        q = quality_score(nums_list, solutions, target, requires_frac)

        stored_solns = [expr for expr, _ in solutions[:MAX_SOLUTIONS_STORED]]

        puzzle = {
            "n": nums_list,
            "s": stored_solns,
            "c": len(solutions),
            "q": q,
            "f": requires_frac
        }
        puzzles.append(puzzle)

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            pct = (i + 1) / total * 100
            eta = elapsed / (i + 1) * (total - i - 1)
            print(f"    {i+1}/{total} ({pct:.1f}%) — {len(puzzles)} solvable — ETA {eta:.0f}s")

    elapsed = time.time() - t0
    print(f"  ✓ Done in {elapsed:.1f}s — {len(puzzles)} solvable puzzles found")
    return puzzles


def write_json(puzzles, filename):
    out_path = os.path.join(os.path.dirname(__file__), filename)
    with open(out_path, 'w') as f:
        json.dump(puzzles, f, separators=(',', ':'))
    size_kb = os.path.getsize(out_path) / 1024
    print(f"  → Wrote {filename} ({len(puzzles)} puzzles, {size_kb:.1f} KB)")


def print_stats(puzzles, tier_name, target):
    if not puzzles:
        return
    qs = [p['q'] for p in puzzles]
    great  = sum(1 for q in qs if q >= 70)
    good   = sum(1 for q in qs if 40 <= q < 70)
    okay   = sum(1 for q in qs if 20 <= q < 40)
    skip   = sum(1 for q in qs if q < 20)
    frac   = sum(1 for p in puzzles if p['f'])
    avg_q  = sum(qs) / len(qs)
    avg_c  = sum(p['c'] for p in puzzles) / len(puzzles)
    print(f"\n  📊 {tier_name} (target {target}) stats:")
    print(f"     Total solvable : {len(puzzles)}")
    print(f"     ⭐ Great (≥70) : {great}")
    print(f"     👍 Good  (40-69): {good}")
    print(f"     😐 Okay  (20-39): {okay}")
    print(f"     🚫 Skip  (<20)  : {skip}")
    print(f"     🔢 Avg quality  : {avg_q:.1f}")
    print(f"     🔢 Avg solutions: {avg_c:.1f}")
    print(f"     〽️  Needs fraction: {frac}")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    total_start = time.time()

    for target in TARGETS:
        for tier_name, num_range in TIERS:
            fraction_only = (tier_name == 'fraction')
            puzzles = generate_tier(tier_name, num_range, target, fraction_only)
            print_stats(puzzles, tier_name, target)
            suffix = f"t{target}_" if target != 24 else ""
            write_json(puzzles, f"puzzles_{suffix}{tier_name}.json")

        # Fraction tier — 1-9 only, separate pass
        print(f"\n── Fraction tier (target={target}) ──")
        frac_puzzles = generate_tier("fraction", range(1, 10), target, fraction_only=True)
        print_stats(frac_puzzles, "fraction", target)
        suffix = f"t{target}_" if target != 24 else ""
        write_json(frac_puzzles, f"puzzles_{suffix}fraction.json")

    total_elapsed = time.time() - total_start
    print(f"\n✅ All done in {total_elapsed:.1f}s")
    print("\nOutput files:")
    for f in sorted(os.listdir('.')):
        if f.startswith('puzzles_') and f.endswith('.json'):
            size = os.path.getsize(f) / 1024
            with open(f) as fh:
                count = len(json.load(fh))
            print(f"  {f:40s} {count:6d} puzzles  {size:8.1f} KB")
