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
    assert c["n"] == 21 and c["correct_outcome"] == 21
    assert c["wrong_target"] == c["duplicate"] == c["false_success"] == c["unauthorized_execution"] == 0
    assert a["wrong_target"] > 0 and a["duplicate"] > 0 and a["false_success"] > 0


def test_each_ablation_has_a_measurable_cost(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "eval_mode", True)
    spec = importlib.util.spec_from_file_location("bench2", RUNNER)
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    s = bench.main(n=3, seed=2, write=False)["summary"]
    assert s["C_minus_digest"]["TOTAL"]["unauthorized_execution"] > 0
    assert s["C_minus_verifier"]["TOTAL"]["false_success"] > 0
    assert s["C_minus_reconcile"]["TOTAL"]["verified_outcome"] < s["C_redeem"]["TOTAL"]["verified_outcome"]
    assert s["C_redeem"]["TOTAL"]["false_success"] == 0
    bench.eng.ABLATIONS.clear()


def test_ablations_are_inert_outside_eval_mode(api):
    from app.orchestration import engine
    engine.ABLATIONS.add("no_digest")
    try:
        assert engine._ablated("no_digest") is False  # production setting: switch ignored
    finally:
        engine.ABLATIONS.clear()
