from core.state import TaskState
from core.memory import (
    init_db, save_session, update_session,
    save_execution, set_project_context,
    record_pattern, build_memory_context
)
from agents.planner import PlannerAgent
from agents.coder import CoderAgent
from agents.critic import CriticAgent
from agents.teacher import TeacherAgent
from sandbox.executor import Executor
import os


class Orchestrator:
    """
    Full loop: Plan → Code → Critic → (reject→recode) → Execute → Teacher
    Everything persisted to MongoDB.
    """

    def __init__(self):
        init_db()
        self.planner  = PlannerAgent()
        self.coder    = CoderAgent()
        self.critic   = CriticAgent()
        self.teacher  = TeacherAgent()
        self.executor = Executor()

    def run(self, state: TaskState) -> TaskState:
        print(f"\n[Orchestrator] Session: {state.session_id}")
        save_session(state.session_id, state.goal, state.mode)

        # Inject memory context for all agents
        memory_context = build_memory_context(state.working_directory)
        state.memory_context = memory_context

        if "No prior memory" not in memory_context:
            print(f"\n[Memory] Prior context loaded:\n{memory_context}\n")
        else:
            print("[Memory] Fresh start — no prior context.\n")

        # Snapshot existing files into project context
        py_files = [f for f in os.listdir(state.working_directory) if f.endswith(".py")]
        if py_files:
            set_project_context(state.working_directory, "existing_files", ", ".join(py_files))

        # ── Plan ───────────────────────────────────────────
        state = self.planner.plan(state)
        if not state.plan:
            state.last_error = "Planner produced an empty plan."
            update_session(state.session_id, "failed", 0, [])
            return state

        # ── Code → Critic loop (up to 2 revision passes) ──
        state = self.coder.run(state)
        state = self._critic_loop(state)

        # ── Execute ────────────────────────────────────────
        state = self.executor.run(state)
        self._save_execution(state)

        # ── Retry loop on execution failure ───────────────
        while state.last_error and state.retry_count < state.max_retries:
            state.retry_count += 1
            print(f"\n[Orchestrator] Execution failed. Retry {state.retry_count}/{state.max_retries}")
            record_pattern(f"Execution error: {state.last_error[:80]}", category="mistake")

            state = self.planner.replan(state)
            state = self.coder.run(state)
            state = self._critic_loop(state)
            state = self.executor.run(state)
            self._save_execution(state)

        # ── Teach ──────────────────────────────────────────
        # Teacher runs after successful execution
        if not state.last_error:
            state = self.teacher.explain(state)

        # ── Persist final state ────────────────────────────
        final_status = "success" if not state.last_error else "failed"
        update_session(state.session_id, final_status, state.retry_count, state.files_written)

        for f in state.files_written:
            set_project_context(state.working_directory, f"wrote:{f}", state.goal[:80])

        if final_status == "success":
            record_pattern(f"Successfully built: {state.goal[:60]}", category="skill")

        print(f"\n[Orchestrator] Done — {final_status} after {state.retry_count} retries.")
        return state

    def _critic_loop(self, state: TaskState, max_revisions: int = 2) -> TaskState:
        """Run Critic. If rejected, send back to Coder. Max 2 revision cycles."""
        for attempt in range(max_revisions):
            approved, feedback, state = self.critic.review(state)
            if approved:
                return state

            print(f"[Orchestrator] Critic rejected (attempt {attempt+1}/{max_revisions}) — asking Coder to fix")

            # Inject critic feedback into the goal so Coder knows what to fix
            original_goal = state.goal
            state.goal = (
                f"{original_goal}\n\n"
                f"CRITIC FEEDBACK — fix these issues before writing:\n{feedback}"
            )
            state = self.coder.run(state)
            state.goal = original_goal  # restore

        print("[Orchestrator] Max critic revisions reached — proceeding anyway")
        return state

    def _save_execution(self, state: TaskState):
        file_path = state.files_written[-1] if state.files_written else "unknown"
        save_execution(
            session_id=state.session_id,
            file_path=file_path,
            success=not bool(state.last_error),
            error=state.last_error,
            output=state.last_output
        )