import json
from openai import OpenAI
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MODELS
from config import MODELS
from core.llm import get_client
from core.state import TaskState
from tools.file_tools import FILE_TOOLS, read_file, list_directory


TOOL_FUNCTIONS = {
    "read_file":       read_file,
    "list_directory":  list_directory,
}


def get_client(provider: str) -> OpenAI:
    if provider == "openrouter":
        return OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
    return OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")


class PlannerAgent:
    """
    Surveys the project and produces a numbered execution plan.
    Re-plans when given an error from the Executor.
    Never writes code — only plans.
    """

    def __init__(self):
        cfg = MODELS["planner"]
        self.provider = cfg["provider"]
        self.model    = cfg["model"]
        self.client   = get_client(self.provider)

    def plan(self, state: TaskState) -> TaskState:
        """Produce a fresh plan for the current goal."""
        print(f"\n[Planner] Planning for: {state.goal}")

        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user",   "content": self._user_prompt(state)}
        ]

        # Planner can read files and list dirs to understand context
        for _ in range(6):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=FILE_TOOLS,
                tool_choice="auto",
                max_tokens=2048,
            )

            msg = response.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                # Parse numbered steps out of the response
                plan = self._parse_plan(msg.content or "")
                state.plan = plan
                state.current_step = 0
                print(f"[Planner] Plan ({len(plan)} steps):")
                for i, step in enumerate(plan, 1):
                    print(f"  {i}. {step}")
                state.add_message("assistant", msg.content or "", agent="planner")
                return state

            # Handle tool calls (read files to understand codebase)
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                fn   = TOOL_FUNCTIONS.get(name)
                result = json.dumps(fn(**args, working_dir=state.working_directory)) if fn else json.dumps({"error": "unknown tool"})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        return state

    def replan(self, state: TaskState) -> TaskState:
        """Called after Executor failure — replan with error context."""
        print(f"\n[Planner] Replanning after error (attempt {state.retry_count}/{state.max_retries})")
        print(f"[Planner] Error was: {state.last_error[:200]}")

        # Inject the failure into the goal context so the model knows what broke
        original_goal = state.goal
        state.goal = (
            f"{original_goal}\n\n"
            f"PREVIOUS ATTEMPT FAILED.\n"
            f"Error:\n{state.last_error}\n\n"
            f"Adjust your plan to fix this specific error."
        )

        state = self.plan(state)
        state.goal = original_goal  # restore clean goal
        return state

    def _system_prompt(self) -> str:
        return """You are a senior software engineer planning coding tasks.

Your job is ONLY to create a clear execution plan — not to write code.

Rules:
- First use list_directory to understand the project structure
- Read relevant existing files if needed to understand context
- Output a numbered list of concrete steps for a Coder agent to follow
- Each step must be a single, specific action
- Maximum 6 steps
- If given an error from a previous attempt, make the first step fix that error

Output format — respond with ONLY the numbered list:
1. Step one
2. Step two"""

    def _user_prompt(self, state: TaskState) -> str:
        memory_section = ""
        if state.memory_context and "No prior memory" not in state.memory_context:
            memory_section = f"\n\nMemory context (use this to inform your plan):\n{state.memory_context}"

        files_context = ""
        if state.files_written:
            files_context = f"\nFiles already written this session: {state.files_written}"

        return (
            f"Goal: {state.goal}\n"
            f"Working directory: {state.working_directory}"
            f"{files_context}"
            f"{memory_section}"
        )

    def _parse_plan(self, text: str) -> list[str]:
        """Extract numbered steps from planner output."""
        steps = []
        for line in text.strip().splitlines():
            line = line.strip()
            # Match lines starting with a number and period/dot
            if line and line[0].isdigit() and len(line) > 2:
                # Strip leading "1. " or "1) "
                step = line.split(".", 1)[-1].strip()
                if not step:
                    step = line.split(")", 1)[-1].strip()
                if step:
                    steps.append(step)
        return steps if steps else [text.strip()]