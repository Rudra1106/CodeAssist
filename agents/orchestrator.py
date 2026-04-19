from core.state import TaskState
from agents.planner import PlannerAgent
from agents.coder import CoderAgent
from sandbox.executor import Executor


class Orchestrator:
    """
    Runs the full Plan → Code → Execute → (retry on failure) loop.
    This is the only class main.py needs to call.
    """

    def __init__(self):
        self.planner  = PlannerAgent()
        self.coder    = CoderAgent()
        self.executor = Executor()

    def run(self, state: TaskState) -> TaskState:
        print("\n[Orchestrator] Starting autonomous loop")
        print(f"[Orchestrator] Max retries: {state.max_retries}\n")

        # Step 1 — Planner surveys the project and makes a plan
        state = self.planner.plan(state)

        if not state.plan:
            print("[Orchestrator] Planner produced no plan. Aborting.")
            state.last_error = "Planner produced an empty plan."
            return state

        # Step 2 — Coder executes the plan
        state = self.coder.run(state)

        # Step 3 — Executor runs the code
        state = self.executor.run(state)

        # Step 4 — Self-correcting retry loop
        while state.last_error and state.retry_count < state.max_retries:
            state.retry_count += 1
            print(f"\n[Orchestrator] Execution failed. Retry {state.retry_count}/{state.max_retries}")
            print(f"[Orchestrator] Error: {state.last_error[:200]}")

            # Planner re-reads the error and updates the plan
            state = self.planner.replan(state)

            # Coder tries again with the new plan
            state = self.coder.run(state)

            # Executor verifies again
            state = self.executor.run(state)

        # Final status
        if state.last_error:
            print(f"\n[Orchestrator] Failed after {state.retry_count} retries.")
            print(f"[Orchestrator] Last error: {state.last_error}")
        else:
            print(f"\n[Orchestrator] Success after {state.retry_count} retries.")

        return state