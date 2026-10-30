import importlib.util
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[3] / "evals" / "runners" / "benchmark.py"


def test_benchmark_regression_guard():
    """Small-n run: REDEEM must stay at zero wrong-target / duplicate / false-success / unauthorized on the
    fixture scenarios, and the naive policy must demonstrably fail (guards against a vacuous benchmark)."""
    spec = importlib.util.spec_from_file_location("bench", RUNNER)
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    r = bench.main(n=3, seed=1, write=False)
    c, a = r["summary"]["C_redeem"]["TOTAL"], r["summary"]["A_naive"]["TOTAL"]
    assert c["n"] == 15 and c["correct_outcome"] == 15
    assert c["wrong_target"] == c["duplicate"] == c["false_success"] == c["unauthorized_execution"] == 0
    assert a["wrong_target"] > 0 and a["duplicate"] > 0 and a["false_success"] > 0
