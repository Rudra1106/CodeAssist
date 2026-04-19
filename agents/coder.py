import json
import os
from openai import OpenAI
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MODELS, FALLBACKS
from core.state import TaskState
from tools.file_tools import FILE_TOOLS, read_file, write_file, list_directory


# Map tool names to actual functions
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "write_file": write_file,
    "list_directory": list_directory,
}


def get_client(provider: str) -> OpenAI:
    """Return the right OpenAI-compatible client for a given provider."""
    if provider == "openrouter":
        return OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL
        )
    elif provider == "ollama":
        return OpenAI(
            api_key="ollama",          # Ollama doesn't need a real key
            base_url="http://localhost:11434/v1"
        )
    raise ValueError(f"Unknown provider: {provider}")


def run_tool_call(tool_name: str, tool_args: dict, working_dir: str) -> str:
    """Execute a tool call and return result as string."""
    func = TOOL_FUNCTIONS.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # Inject working_dir into every tool call
    result = func(**tool_args, working_dir=working_dir)
    return json.dumps(result)


class CoderAgent:
    """
    The Coder agent. Receives a task, uses file tools to read
    context, then writes the implementation.
    """

    def __init__(self):
        cfg = MODELS["coder"]
        self.provider = cfg["provider"]
        self.model = cfg["model"]
        self.client = get_client(self.provider)

    def run(self, state: TaskState) -> TaskState:
        """Run the coder agent on the current task state."""
        print(f"\n[Coder] Starting task: {state.goal}")
        print(f"[Coder] Using model: {self.model} via {self.provider}\n")

        # Build the system prompt
        system_prompt = self._build_system_prompt(state)

        # Initial message from user (the task)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"Task: {state.goal}\n\nWorking directory: {state.working_directory}"}
        ]

        # Agentic loop — keep going until model stops calling tools
        max_iterations = 10
        for iteration in range(max_iterations):
            print(f"[Coder] Iteration {iteration + 1}...")

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=FILE_TOOLS,
                    tool_choice="auto",
                    max_tokens=4096,
                )
            except Exception as e:
                print(f"[Coder] Error calling {self.provider}: {e}")
                # Try fallback
                state = self._try_fallback(state, messages, str(e))
                break

            choice = response.choices[0]
            msg = choice.message

            # Add assistant message to history
            messages.append(msg.model_dump(exclude_none=True))

            # If no tool calls, the agent is done
            if not msg.tool_calls:
                final_text = msg.content or ""
                print(f"[Coder] Done.\n{final_text}")
                state.add_message("assistant", final_text, agent="coder")
                state.last_output = final_text
                break

            # Process each tool call
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)

                print(f"[Coder] Tool call → {name}({args})")

                result = run_tool_call(name, args, state.working_directory)
                result_data = json.loads(result)

                # Track what was read/written
                if name == "read_file" and result_data.get("success"):
                    state.files_read.append(args.get("path", ""))
                if name == "write_file" and result_data.get("success"):
                    state.files_written.append(args.get("path", ""))
                    print(f"[Coder] Wrote → {args.get('path')}")

                # Feed tool result back into the conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

        return state

    def _build_system_prompt(self, state: TaskState) -> str:
        mode_instruction = (
            "After writing code, explain what you did and why in simple terms."
            if state.mode == "learner"
            else "Be concise. Write the code. Minimal commentary."
        )

        return f"""You are an expert Python developer acting as a coding assistant.
You have access to file tools to read, write, and list files.

Your job:
1. First, list the directory to understand the project structure
2. Read any relevant existing files
3. Write the implementation to complete the task
4. {mode_instruction}

Rules:
- Always list the directory first before reading files
- Write complete, working code — no placeholders or TODOs
- Use modern Python (3.11+) with type hints
- Handle errors properly
- One file write per logical unit of code
"""

    def _try_fallback(self, state: TaskState, messages: list, error: str) -> TaskState:
        """Attempt to use fallback model if primary fails."""
        fallback = FALLBACKS.get(self.provider)
        if not fallback:
            state.last_error = error
            return state

        print(f"[Coder] Falling back to {fallback['provider']}/{fallback['model']}")
        try:
            client = get_client(fallback["provider"])
            response = client.chat.completions.create(
                model=fallback["model"],
                messages=messages,
                tools=FILE_TOOLS,
                tool_choice="auto",
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
            state.last_output = content
            state.add_message("assistant", content, agent="coder_fallback")
        except Exception as e2:
            state.last_error = str(e2)
        return state
    
    # ! there's a subtle bug in agents/coder.py in the _try_fallback method. When it falls back to Ollama, it still passes tools=FILE_TOOLS but small Ollama models don't reliably support tool use either. Replace _try_fallback with this safer version that strips tools and just asks for a plain response:
    # def _try_fallback(self, state: TaskState, messages: list, error: str) -> TaskState:
    #     """Attempt to use fallback model if primary fails."""
    #     fallback = FALLBACKS.get(self.provider)
    #     if not fallback:
    #         state.last_error = error
    #         return state

    #     print(f"[Coder] Falling back to {fallback['provider']}/{fallback['model']}")
    #     try:
    #         client = get_client(fallback["provider"])
    #         # Fallback: no tool calls, just ask for raw code as text
    #         # Small local models can't reliably do tool use
    #         fallback_messages = [
    #             messages[0],  # keep system prompt
    #             {
    #                 "role": "user",
    #                 "content": (
    #                     f"{messages[1]['content']}\n\n"
    #                     "Respond with the complete Python code only. "
    #                     "I will save it manually. No tool calls needed."
    #                 )
    #             }
    #         ]
    #         response = client.chat.completions.create(
    #             model=fallback["model"],
    #             messages=fallback_messages,
    #             max_tokens=2048,
    #         )
    #         content = response.choices[0].message.content or ""
    #         print(f"[Coder] Fallback response received.")
    #         state.last_output = content
    #         state.add_message("assistant", content, agent="coder_fallback")
    #     except Exception as e2:
    #         state.last_error = str(e2)
    #         print(f"[Coder] Fallback also failed: {e2}")
    #     return state