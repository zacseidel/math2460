"""
Math 24/60 Puzzle Library Generator  (fast version)
=====================================================
Exhaustively finds all solvable 4-number combinations for each difficulty tier,
computes fun/quality scores, and outputs per-tier JSON files.

Output files (placed in same directory as this script):
  puzzles_easy.json        1-9,  target 24
  puzzles_medium.json      1-19, target 24
  puzzles_hard.json        1-29, target 24
  puzzles_expert.json      1-49, target 24
  puzzles_extreme.json     1-49, target 24  (same range, kept as separate tier)
  puzzles_fraction.json    1-9,  target 24, fraction-only puzzles
  puzzles_t60_*.json       same tiers, target 60

Each puzzle entry:
  {
    "n": [a, b, c, d],
    "s": ["expr1", "expr2", "expr3"],  # up to 3 solutions (display format)
    "c": <total distinct solution count>,
    "q": <quality score 0-100>,
    "f": <true if ALL solutions require an intermediate fraction>
  }

Solver approach:
  - All 24 permutations of [a,b,c,d]
  - All 4^3 = 64 operator triples (no division by zero)
  - All 5 distinct parenthesization templates
  = 7,680 expression evaluations per combo, guaranteed complete, no duplicates.

Uses Python's Fraction for exact arithmetic (no floating point errors).

Usage:
  python generate_puzzles.py

Estimated runtimes on a modern laptop:
  Easy   (495 combos)        ~1s
  Medium (~4,845 combos)     ~8s
  Hard   (~27,405 combos)    ~45s
  Expert (~211,876 combos)   ~6 min
  Extreme (same as expert)   ~6 min
  Fraction tiers             fast subset of the above
  Total for both targets:    ~25 min
"""

import itertools
import json
import math
import os
import sys
import time
from collections import Counter
from fractions import Fraction

# ── Configuration ─────────────────────────────────────────────────────────────

TIERS = [
    ("easy",     range(1, 10)),   # 495 combos
    ("medium",   range(1, 20)),   # 4,845 combos
    ("hard",     range(1, 30)),   # 27,405 combos
    ("expert",   range(1, 50)),   # 211,876 combos
    ("extreme",  range(1, 50)),   # 211,876 combos (same range, separate tier slot)
    ("fraction", range(1, 10)),   # subset of easy — fraction-required only
]

TARGETS            = [24, 60]
MAX_SOLUTIONS      = 3      # max solutions stored in JSON
MIN_QUALITY        = 20     # puzzles below this are excluded entirely
PRINT_INTERVAL     = 2000   # print progress every N combos

# ── Solver ────────────────────────────────────────────────────────────────────
#
# We use the 5-template approach. For 4 numbers a,b,c,d (already permuted),
# the 5 distinct binary-tree shapes are:
#
#   T0:  ((a ○ b) ○ c) ○ d
#   T1:  (a ○ (b ○ c)) ○ d
#   T2:  (a ○ b) ○ (c ○ d)
#   T3:  a ○ ((b ○ c) ○ d)
#   T4:  a ○ (b ○ (c ○ d))
#
# We evaluate each using Fraction arithmetic so results are exact.
# Display strings use Unicode symbols ×, ÷, − for the HTML game.

OPS_EVAL  = ('+', '-', '*', '/')
OPS_DISP  = {'+':'+', '-':'−', '*':'×', '/':'÷'}
F0        = Fraction(0)

def _op(a, b, op):
    """Apply op to Fractions; return None on division by zero."""
    if op == '+': return a + b
    if op == '-': return a - b
    if op == '*': return a * b
    # division
    if b == F0:   return None
    return a / b

def _d(sym):
    return OPS_DISP[sym]

def solve(numbers, target):
    """
    Find all distinct solutions for `numbers` (list of 4 ints) reaching `target`.

    Returns:
      solutions  : list of (display_string, uses_fraction_bool)
      total_count: int — number of distinct solutions found
    """
    target_f = Fraction(target)
    fracs    = [Fraction(n) for n in numbers]

    seen      = set()   # deduplicate by display string (spaces stripped)
    solutions = []

    for perm in itertools.permutations(fracs):
        a, b, c, d = perm
        # Label strings for each number
        sa = str(int(a)) if a.denominator == 1 else str(a)
        sb = str(int(b)) if b.denominator == 1 else str(b)
        sc = str(int(c)) if c.denominator == 1 else str(c)
        sd = str(int(d)) if d.denominator == 1 else str(d)

        for o1 in OPS_EVAL:
            ab = _op(a, b, o1)
            if ab is None: continue
            f_ab = (ab.denominator != 1)

            for o2 in OPS_EVAL:
                bc = _op(b, c, o2)
                if bc is None: continue

                abc_t0 = _op(ab, c, o2)   # T0 middle step
                abc_t1 = _op(a, bc, o1)   # T1 middle step (reusing o1 slot logically)

                for o3 in OPS_EVAL:

                    # T0: ((a o1 b) o2 c) o3 d
                    if abc_t0 is not None:
                        v = _op(abc_t0, d, o3)
                        if v == target_f:
                            frac = f_ab or (abc_t0.denominator != 1) or (v.denominator != 1)
                            expr = f"(({sa}{_d(o1)}{sb}){_d(o2)}{sc}){_d(o3)}{sd}"
                            key  = expr.replace(' ','')
                            if key not in seen:
                                seen.add(key)
                                solutions.append((expr, frac))

                    # T1: (a o1 (b o2 c)) o3 d
                    if bc is not None:
                        ab_bc = _op(a, bc, o1)
                        if ab_bc is not None:
                            v = _op(ab_bc, d, o3)
                            if v == target_f:
                                frac = (bc.denominator != 1) or (ab_bc.denominator != 1) or (v.denominator != 1)
                                expr = f"({sa}{_d(o1)}({sb}{_d(o2)}{sc})){_d(o3)}{sd}"
                                key  = expr.replace(' ','')
                                if key not in seen:
                                    seen.add(key)
                                    solutions.append((expr, frac))

                    # T2: (a o1 b) o2 (c o3 d)
                    cd = _op(c, d, o3)
                    if cd is not None and ab is not None:
                        v = _op(ab, cd, o2)
                        if v == target_f:
                            frac = f_ab or (cd.denominator != 1) or (v.denominator != 1)
                            expr = f"({sa}{_d(o1)}{sb}){_d(o2)}({sc}{_d(o3)}{sd})"
                            key  = expr.replace(' ','')
                            if key not in seen:
                                seen.add(key)
                                solutions.append((expr, frac))

                    # T3: a o1 ((b o2 c) o3 d)
                    if bc is not None:
                        bcd = _op(bc, d, o3)
                        if bcd is not None:
                            v = _op(a, bcd, o1)
                            if v == target_f:
                                frac = (bc.denominator != 1) or (bcd.denominator != 1) or (v.denominator != 1)
                                expr = f"{sa}{_d(o1)}(({sb}{_d(o2)}{sc}){_d(o3)}{sd})"
                                key  = expr.replace(' ','')
                                if key not in seen:
                                    seen.add(key)
                                    solutions.append((expr, frac))

                    # T4: a o1 (b o2 (c o3 d))
                    cd = _op(c, d, o3)
                    if cd is not None:
                        bcd2 = _op(b, cd, o2)
                        if bcd2 is not None:
                            v = _op(a, bcd2, o1)
                            if v == target_f:
                                frac = (cd.denominator != 1) or (bcd2.denominator != 1) or (v.denominator != 1)
                                expr = f"{sa}{_d(o1)}({sb}{_d(o2)}({sc}{_d(o3)}{sd}))"
                                key  = expr.replace(' ','')
                                if key not in seen:
                                    seen.add(key)
                                    solutions.append((expr, frac))

    return solutions, len(solutions)


# ── Quality Score ─────────────────────────────────────────────────────────────

def quality_score(numbers, solutions, total_count, target):
    """
    Returns integer quality score 0-100.

    Components:
      Base score            : 50
      Target-in-set penalty : -40  (e.g. [1,1,1,24] is trivial)
      Solution count        : ±15  sweet spot 2-8, penalise extremes
      Operator variety      : +20  best solution uses − or ÷
      Identity abuse        : -10  max mild penalty for ×1 / +0
      Number spread         : +20  std dev reward
      Repetition            : -15  max mild penalty
      Meaningful use        : +15  no ×1 or +0 in any stored solution
    """
    score = 50

    # 1. Target appears directly in the number set
    if target in numbers:
        score -= 40

    # 2. Solution count — sweet spot 2–8
    c = total_count
    if   c == 1:      score += 10 - 15   # rare, not bad but not great
    elif c <= 8:      score += 25 - 15   # sweet spot
    elif c <= 20:     score += 12 - 15
    elif c <= 50:     score += 5  - 15
    else:             score += 0  - 15   # too easy

    # 3. Operator variety across first 5 solutions
    has_sub = has_div = False
    for expr, _ in solutions[:5]:
        if '−' in expr: has_sub = True
        if '÷' in expr: has_div = True
    if has_sub: score += 10
    if has_div: score += 10

    # 4. Multiplicative identity / additive zero abuse (mild)
    ones  = numbers.count(1)
    zeros = numbers.count(0)
    score -= min(10, ones * 3 + zeros * 5)

    # 5. Number spread (std deviation)
    mean = sum(numbers) / 4
    var  = sum((x - mean) ** 2 for x in numbers) / 4
    std  = math.sqrt(var)
    score += min(20, int(std * 1.5))

    # 6. Repetition penalty (mild)
    max_rep = max(Counter(numbers).values())
    if   max_rep == 4: score -= 15
    elif max_rep == 3: score -= 8
    elif max_rep == 2: score -= 3

    # 7. Meaningful use bonus
    trivial = any(
        '×1' in e or '1×' in e or '+0' in e or '0+' in e
        for e, _ in solutions[:3]
    )
    if not trivial:
        score += 15

    return max(0, min(100, score))


# ── Tier Generation ───────────────────────────────────────────────────────────

def generate_tier(tier_name, num_range, target, fraction_only=False):
    combos = list(itertools.combinations_with_replacement(num_range, 4))
    total  = len(combos)
    puzzles = []
    t0 = time.time()

    print(f"\n  [{tier_name}] target={target} | {total:,} combos", flush=True)

    for i, nums in enumerate(combos):
        nums_list = list(nums)
        solutions, count = solve(nums_list, target)

        if not solutions:
            if (i+1) % PRINT_INTERVAL == 0:
                _progress(i+1, total, len(puzzles), t0)
            continue

        # fraction_only: skip if no solution requires a fraction
        any_frac  = any(f for _, f in solutions)
        all_frac  = all(f for _, f in solutions)
        if fraction_only and not any_frac:
            if (i+1) % PRINT_INTERVAL == 0:
                _progress(i+1, total, len(puzzles), t0)
            continue

        q = quality_score(nums_list, solutions, count, target)
        if q < MIN_QUALITY:
            if (i+1) % PRINT_INTERVAL == 0:
                _progress(i+1, total, len(puzzles), t0)
            continue

        stored = [expr for expr, _ in solutions[:MAX_SOLUTIONS]]

        puzzles.append({
            "n": nums_list,
            "s": stored,
            "c": count,
            "q": q,
            "f": any_frac,
        })

        if (i+1) % PRINT_INTERVAL == 0:
            _progress(i+1, total, len(puzzles), t0)

    elapsed = time.time() - t0
    print(f"  ✓ {elapsed:.1f}s — {len(puzzles):,} puzzles kept", flush=True)
    return puzzles


def _progress(done, total, kept, t0):
    elapsed = time.time() - t0
    eta     = elapsed / done * (total - done) if done else 0
    pct     = done / total * 100
    print(f"    {done:>7,}/{total:,} ({pct:.1f}%)  kept={kept:,}  ETA {eta:.0f}s", flush=True)


# ── Stats printer ─────────────────────────────────────────────────────────────

def print_stats(puzzles, tier_name, target):
    if not puzzles:
        print(f"  ⚠  No puzzles found for {tier_name} target={target}")
        return
    qs    = [p['q'] for p in puzzles]
    great = sum(1 for q in qs if q >= 70)
    good  = sum(1 for q in qs if 40 <= q < 70)
    okay  = sum(1 for q in qs if 20 <= q < 40)
    frac  = sum(1 for p in puzzles if p['f'])
    avg_q = sum(qs) / len(qs)
    avg_c = sum(p['c'] for p in puzzles) / len(puzzles)
    print(f"  📊 {tier_name}/t{target}: {len(puzzles):,} total | "
          f"⭐{great} 👍{good} 😐{okay} | "
          f"avg quality={avg_q:.0f} avg solutions={avg_c:.1f} fractions={frac}")


# ── Write JSON ────────────────────────────────────────────────────────────────

def write_json(puzzles, filename):
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    with open(out, 'w') as f:
        json.dump(puzzles, f, separators=(',', ':'))
    kb = os.path.getsize(out) / 1024
    print(f"  → {filename}  ({len(puzzles):,} puzzles, {kb:.0f} KB)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    total_start = time.time()
    output_files = []

    for target in TARGETS:
        print(f"\n{'═'*55}")
        print(f"  TARGET = {target}")
        print(f"{'═'*55}")

        for tier_name, num_range in TIERS:
            fraction_only = (tier_name == 'fraction')
            puzzles = generate_tier(tier_name, num_range, target, fraction_only)
            print_stats(puzzles, tier_name, target)
            prefix   = f"puzzles_t{target}_" if target != 24 else "puzzles_"
            filename = f"{prefix}{tier_name}.json"
            write_json(puzzles, filename)
            output_files.append(filename)

    total = time.time() - total_start
    mins, secs = divmod(int(total), 60)
    print(f"\n{'═'*55}")
    print(f"  ✅ All done in {mins}m {secs}s")
    print(f"{'═'*55}")
    print("\nOutput files:")
    for fn in output_files:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fn)
        if os.path.exists(path):
            kb    = os.path.getsize(path) / 1024
            with open(path) as fh:
                count = len(json.load(fh))
            print(f"  {fn:40s}  {count:7,} puzzles  {kb:8.0f} KB")


if __name__ == '__main__':
    main()
