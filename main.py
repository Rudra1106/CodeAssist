import sys
import os
from core.state import TaskState
from agents.coder import CoderAgent


def main():
    # Create a test project directory
    test_dir = "./test_project"
    os.makedirs(test_dir, exist_ok=True)

    # Define a task
    goal = sys.argv[1] if len(sys.argv) > 1 else (
        "Create a Python file called calculator.py with functions for "
        "add, subtract, multiply, and divide. Include proper error handling "
        "for division by zero and type checking."
    )

    # Build initial state
    state = TaskState(
        goal=goal,
        working_directory=test_dir,
        mode="learner"   # change to "pro" for terse output
    )

    print("=" * 60)
    print(f"ATLAS — Autonomous Coding Assistant")
    print(f"Mode: {state.mode}")
    print(f"Task: {state.goal}")
    print("=" * 60)

    # Run the coder agent
    agent = CoderAgent()
    state = agent.run(state)

    # Show results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Files read:    {state.files_read}")
    print(f"Files written: {state.files_written}")
    if state.last_error:
        print(f"Error: {state.last_error}")
    if state.last_output:
        print(f"\nAgent output:\n{state.last_output}")


if __name__ == "__main__":
    main()