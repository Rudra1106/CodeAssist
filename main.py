import sys
import os
from core.state import TaskState
from agents.coder import CoderAgent
from sandbox.executor import Executor


def main():
    test_dir = "./test_project"
    os.makedirs(test_dir, exist_ok=True)

    goal = sys.argv[1] if len(sys.argv) > 1 else (
        "Create a Python file called calculator.py with functions for "
        "add, subtract, multiply, and divide. Include a main block at the "
        "bottom that demonstrates each function with print statements."
    )

    state = TaskState(
        goal=goal,
        working_directory=test_dir,
        mode="learner"
    )

    print("=" * 60)
    print("ATLAS — Autonomous Coding Assistant")
    print(f"Mode:  {state.mode}")
    print(f"Task:  {state.goal}")
    print("=" * 60)

    # Phase 1: Coder writes the file
    coder = CoderAgent()
    state = coder.run(state)

    if state.last_error and not state.files_written:
        print(f"\n[Main] Coder failed with no output: {state.last_error}")
        return

    # Phase 2: Executor runs it
    print("\n" + "-" * 60)
    print("EXECUTOR — Running code in Docker sandbox")
    print("-" * 60)

    executor = Executor()
    state = executor.run(state)

    # Final summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Files written:  {state.files_written}")

    if state.last_error:
        print(f"\nExecution error:\n{state.last_error}")
        print("\n[Next] In Phase 3, the Planner will read this error and retry.")
    else:
        print(f"\nExecution output:\n{state.last_output}")
        print("\n[Success] Code written and verified.")


if __name__ == "__main__":
    main()