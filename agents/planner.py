import json
from config import MODELS
from core.llm import get_client
from core.state import TaskState
from core.logger import log, log_dim, log_success, log_error, log_plan, log_tool_call, log_tool_result, log_iteration
from tools.file_tools import FILE_TOOLS, read_file, list_directory

TOOL_FUNCTIONS = {
    "read_file":      read_file,
    "list_directory": list_directory,
}


class PlannerAgent:

    def __init__(self):
        cfg = MODELS["planner"]
        self.provider = cfg["provider"]
        self.model    = cfg["model"]
        self.client   = get_client(self.provider)

    def plan(self, state: TaskState) -> TaskState:
        log("planner", f"Planning — model: {self.model}")
        log_dim("planner", f"Goal: {state.goal[:80]}")
        return self._run_planning(state, replan=False)

    def replan(self, state: TaskState) -> TaskState:
        log("planner", f"Replanning after error (attempt {state.retry_count}/{state.max_retries})")
        log_dim("planner", f"Error was: {state.last_error[:120]}")
        original_goal = state.goal
        state.goal = (
            f"{original_goal}\n\nPREVIOUS ATTEMPT FAILED.\n"
            f"Error:\n{state.last_error}\n\nFix this specific error."
        )
        state = self._run_planning(state, replan=True)
        state.goal = original_goal
        return state

    def _run_planning(self, state: TaskState, replan: bool) -> TaskState:
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user",   "content": self._user_prompt(state)}
        ]

        for iteration in range(6):
            log_iteration("planner", iteration + 1)

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=FILE_TOOLS,
                tool_choice="auto",
                max_tokens=2048,
            )

            msg = response.choices[0].message
            log_dim("planner", f"finish_reason: {response.choices[0].finish_reason}")
            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                content = msg.content or ""
                plan = self._parse_plan(content)
                state.plan = plan
                state.current_step = 0
                log_plan(plan)
                state.add_message("assistant", content, agent="planner")
                return state

            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                log_tool_call("planner", name, args)
                fn     = TOOL_FUNCTIONS.get(name)
                result = json.dumps(fn(**args, working_dir=state.working_directory)) if fn else json.dumps({"error": "unknown"})
                result_data = json.loads(result)
                log_tool_result("planner", name, result_data)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        log_error("planner", "Max iterations reached without producing a plan.")
        return state

    def _system_prompt(self) -> str:
        return """You are a senior software engineer planning coding tasks.
Output ONLY a numbered list of steps. No prose, no explanation.
Rules:
- list_directory first to understand the project
- Max 6 steps, each a single concrete action
- If given an error, first step must fix it

Format:
1. Step one
2. Step two"""

    def _user_prompt(self, state: TaskState) -> str:
        memory_section = ""
        if state.memory_context and "No prior memory" not in state.memory_context:
            memory_section = f"\n\nMemory:\n{state.memory_context}"
        files_context = f"\nFiles written: {state.files_written}" if state.files_written else ""
        return (
            f"Goal: {state.goal}\n"
            f"Working directory: {state.working_directory}"
            f"{files_context}{memory_section}"
        )

    def _parse_plan(self, text: str) -> list[str]:
        steps = []
        for line in text.strip().splitlines():
            line = line.strip()
            if line and line[0].isdigit() and len(line) > 2:
                step = line.split(".", 1)[-1].strip()
                if step:
                    steps.append(step)
        return steps if steps else [text.strip()]