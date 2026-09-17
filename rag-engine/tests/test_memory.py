"""Tests for SQLite Session Memory and Trajectory Logging."""

from ragfilings.pipeline.memory import SessionMemoryManager


def test_session_memory_lifecycle(tmp_path):
    db_file = tmp_path / "test_memory.db"
    mem = SessionMemoryManager(db_path=db_file)

    mem.save_session(
        session_id="sess_test_123",
        query="What was Apple's FY2025 net sales?",
        final_answer="$416,161",
        verified=True,
        strategy="agent_react",
        cost_usd=0.0005,
        latency_ms=1250.0,
    )

    mem.log_step(
        session_id="sess_test_123",
        step_index=1,
        agent_name="LeadOrchestrator",
        action="plan_workflow",
        payload={"intent": "lookup"},
    )

    mem.log_step(
        session_id="sess_test_123",
        step_index=2,
        agent_name="Researcher",
        action="retrieve_hybrid",
        payload={"hits": 3},
    )

    traj = mem.get_trajectory("sess_test_123")
    assert len(traj) == 2
    assert traj[0]["agent_name"] == "LeadOrchestrator"
    assert traj[1]["agent_name"] == "Researcher"
    assert traj[0]["payload"]["intent"] == "lookup"
