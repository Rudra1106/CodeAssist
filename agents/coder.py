import json
from config import MODELS, FALLBACKS
from core.llm import get_client
from core.state import TaskState
from core.logger import (
    log, log_dim, log_success, log_error, log_warn,
    log_tool_call, log_tool_result, log_code, log_iteration
)
from tools.file_tools import FILE_TOOLS, read_file, write_file, list_directory

TOOL_FUNCTIONS = {
    "read_file":      read_file,
    "write_file":     write_file,
    "list_directory": list_directory,
}


class CoderAgent:

    def __init__(self):
        cfg = MODELS["coder"]
        self.provider = cfg["provider"]
        self.model    = cfg["model"]
        self.client   = get_client(self.provider)

    def run(self, state: TaskState) -> TaskState:
        log("coder", f"Starting — model: {self.model}")
        log_dim("coder", f"Goal: {state.goal[:80]}")

        messages = [
            {"role": "system", "content": self._build_system_prompt(state)},
            {"role": "user",   "content": f"Task: {state.goal}\nWorking directory: {state.working_directory}"}
        ]

        for iteration in range(10):
            log_iteration("coder", iteration + 1)

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=FILE_TOOLS,
                    tool_choice="auto",
                    max_tokens=4096,
                )
            except Exception as e:
                log_error("coder", f"API error: {e}")
                return self._try_fallback(state, messages, str(e))

            choice = response.choices[0]
            msg    = choice.message

            # Show finish reason so we understand why the model stopped
            log_dim("coder", f"finish_reason: {choice.finish_reason}")

            messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                # Model is done — show its final reasoning
                final = msg.content or ""
                if final:
                    log_success("coder", "Done writing.")
                    # Show a short preview of what the agent said
                    for line in final.splitlines()[:6]:
                        log_dim("coder", line)
                state.last_output = final
                state.add_message("assistant", final, agent="coder")
                break

            # Process tool calls
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)

                log_tool_call("coder", name, args)

                result     = self._run_tool(name, args, state.working_directory)
                result_data = json.loads(result)

                log_tool_result("coder", name, result_data)

                # Track file operations in state
                if name == "write_file" and result_data.get("success"):
                    path = args.get("path", "")
                    state.files_written.append(path)
                    # Show the code that was written
                    log_code("coder", path, args.get("content", ""))

                if name == "read_file" and result_data.get("success"):
                    state.files_read.append(args.get("path", ""))

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result
                })

        return state

    def _run_tool(self, name: str, args: dict, working_dir: str) -> str:
        fn = TOOL_FUNCTIONS.get(name)
        if not fn:
            return json.dumps({"error": f"Unknown tool: {name}"})
        return json.dumps(fn(**args, working_dir=working_dir))

    def _build_system_prompt(self, state: TaskState) -> str:
        mode_instruction = (
            "After writing code, briefly explain what you did and why."
            if state.mode == "learner"
            else "Be concise. Write the code."
        )
        memory = f"\n\nMemory context:\n{state.memory_context}" if state.memory_context else ""
        return f"""
        You are an expert Python developer.
        You have access to file tools to read, write, and list files.
        Your job:
        1. First, list the directory to understand the project structure
        2. Read any relevant existing files
        3. Write the implementation to complete the task
        Use file tools to read context then write the implementation.
        Always list_directory first, then read relevant files, then write.
        {mode_instruction}{memory}"""

    def _try_fallback(self, state: TaskState, messages: list, error: str) -> TaskState:
        fallback = FALLBACKS.get(self.provider)
        if not fallback:
            state.last_error = error
            return state

        log_warn("coder", f"Falling back to {fallback['provider']}/{fallback['model']}")
        try:
            client = get_client(fallback["provider"])
            response = client.chat.completions.create(
                model=fallback["model"],
                messages=[
                    messages[0],
                    {"role": "user", "content": (
                        f"{messages[1]['content']}\n\n"
                        "Respond with complete Python code only."
                    )}
                ],
                max_tokens=2048,
            )
            content = response.choices[0].message.content or ""
            log_success("coder", "Fallback response received.")
            state.last_output = content
            state.add_message("assistant", content, agent="coder_fallback")
        except Exception as e2:
            log_error("coder", f"Fallback also failed: {e2}")
            state.last_error = str(e2)
        return state