"""Ensure raw GWO counts exclude refinement without changing search decisions."""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sim.optimizer import search, GWOParams

def test_separate_callback_preserves_search_result():
    def run(split):
        counts = {"raw": 0, "local": 0}
        def score(b, u):
            j = float(np.sum(u*u))
            # Always supply the same feasible radial incumbent to refinement.
            return j, j, np.zeros(20), np.array([1, 1, 0], dtype=np.int8)
        def fitness(b, u):
            counts["raw"] += 1
            return score(b, u)
        def local(b, u):
            counts["local"] += 1
            return score(b, u)
        result = search(
            fitness, np.array([1, 1, 0], dtype=np.int8), np.arange(3),
            np.zeros((1, 1)), np.random.default_rng(42),
            GWOParams(agents=3, max_iter=1, stagnation=1, ls_max_passes=1),
            topo=(np.array([0, 1, 0]), np.array([1, 2, 2]), 3, np.ones(3, bool)),
            local_fitness=local if split else None)
        return result, counts
    separated, sc = run(True)
    combined, cc = run(False)
    assert sc["raw"] == 6
    assert sc["local"] > 0
    assert cc["raw"] == sc["raw"] + sc["local"]
    assert separated[-1] == combined[-1] == cc["raw"]
    np.testing.assert_array_equal(separated[0], combined[0])
    np.testing.assert_array_equal(separated[1], combined[1])
    assert separated[2][0] == combined[2][0]

if __name__ == "__main__":
    test_separate_callback_preserves_search_result()
    print("PASS: separate counters preserve search result and total evaluations")
