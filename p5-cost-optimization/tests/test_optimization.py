"""Unit tests for Project 5 Cost & Latency Optimization Roadmap Schema."""

from optimization.optimizer import (
    OptimizationStepResult,
    OptimizationTargetReport,
    SystemOptimizerEngine,
)


def test_optimization_target_report_schema():
    """Verify that SystemOptimizerEngine outputs a schema-validated roadmap target structure."""
    engine = SystemOptimizerEngine()
    report = engine.get_illustrative_benchmark_targets()

    # Schema type assertions
    assert isinstance(report, OptimizationTargetReport)
    assert isinstance(report.baseline, OptimizationStepResult)
    assert len(report.optimized_steps) == 4

    # Structure assertions for progression
    for step in report.optimized_steps:
        assert isinstance(step, OptimizationStepResult)
        assert step.cost_reduction_pct >= 0.0
        assert step.latency_reduction_pct >= 0.0

    # Summary integrity
    assert "quality_held" in report.final_summary
    assert "total_cost_saved_pct" in report.final_summary


def test_optimization_backward_compatibility_alias():
    """Verify run_full_benchmark() alias continues to function for backward compatibility."""
    engine = SystemOptimizerEngine()
    report = engine.run_full_benchmark()
    assert isinstance(report, OptimizationTargetReport)
    assert len(report.optimized_steps) == 4
