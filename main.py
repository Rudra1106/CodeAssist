import sys
import os
from core.state import TaskState
from agents.orchestrator import Orchestrator
from ui.app import AtlasApp



def main():
    
    working_dir = sys.argv[1] if len(sys.argv) > 1 else "./test_project"
    os.makedirs(working_dir, exist_ok=True)
    app = AtlasApp(working_dir=working_dir)
    app.run()

    test_dir = "./test_project"
    os.makedirs(test_dir, exist_ok=True)

    goal = sys.argv[1] if len(sys.argv) > 1 else (
        "Create a file called string_utils.py with three functions: "
        "reverse_string, count_vowels, and is_palindrome. "
        "Add a main block that tests all three functions with examples and prints the results."
    )

    state = TaskState(
        goal=goal,
        working_directory=test_dir,
        mode="learner",
        max_retries=3,
    )

    print("=" * 60)
    print("ATLAS — Autonomous Coding Assistant")
    print(f"Mode:  {state.mode}")
    print(f"Task:  {state.goal}")
    print("=" * 60)

    orchestrator = Orchestrator()
    state = orchestrator.run(state)

    # Final summary
    print("\n" + "=" * 60)
    print("SESSION SUMMARY")
    print("=" * 60)
    print(f"Files written:  {state.files_written}")
    print(f"Retries used:   {state.retry_count}/{state.max_retries}")

    if state.last_error:
        print(f"Final status:   FAILED")
        print(f"Last error:     {state.last_error}")
    else:
        print(f"Final status:   SUCCESS")
        print(f"Output:\n{state.last_output}")


if __name__ == "__main__":
    main()