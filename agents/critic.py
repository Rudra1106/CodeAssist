import json
from core.llm import get_client
from core.state import TaskState
from core.memory import record_pattern, get_execution_history
from config import MODELS
from tools.file_tools import read_file


class CriticAgent:
    """
    Reviews code written by the Coder before it gets executed.
    Looks for bugs, bad patterns, missing error handling.
    Can APPROVE or REJECT — rejection sends back to Coder with notes.
    Uses a local Ollama model — runs on every save, zero API cost.
    """

    def __init__(self):
        cfg = MODELS["critic"]
        self.provider = cfg["provider"]
        self.model    = cfg["model"]
        self.client   = get_client(self.provider)

    def review(self, state: TaskState) -> tuple[bool, str, TaskState]:
        """
        Returns (approved: bool, feedback: str, state).
        approved=True  → proceed to Executor
        approved=False → send feedback back to Coder for a fix
        """
        if not state.files_written:
            return True, "No files to review.", state

        target = state.files_written[-1]
        print(f"\n[Critic] Reviewing: {target}")

        # Read the file content
        result = read_file(target, working_dir=state.working_directory)
        if not result["success"]:
            # Can't read it — let it pass, Executor will catch real errors
            return True, f"Could not read file: {result['error']}", state

        code = result["content"]

        # Check execution history — has this file failed before?
        history = get_execution_history(target, limit=3)
        past_errors = [h["error"] for h in history if not h["success"] and h["error"]]

        prompt = self._build_review_prompt(code, target, past_errors, state.goal)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user",   "content": prompt}
                ],
                max_tokens=1024,
            )
            review_text = response.choices[0].message.content or ""
        except Exception as e:
            print(f"[Critic] Model error: {e} — auto-approving")
            return True, f"Critic unavailable: {e}", state

        # Parse verdict from response
        approved = self._parse_verdict(review_text)

        if approved:
            print(f"[Critic] APPROVED")
            record_pattern("Code passed critic review", category="skill")
        else:
            print(f"[Critic] REJECTED — sending feedback to Coder")
            print(f"[Critic] Feedback: {review_text[:300]}")
            record_pattern(
                f"Critic rejected: {review_text[:60]}",
                category="mistake"
            )

        state.add_message("assistant", review_text, agent="critic")
        return approved, review_text, state

    def _system_prompt(self) -> str:
        return """You are a strict but fair senior code reviewer.

Review the given Python code and respond in this exact format:

VERDICT: APPROVE
or
VERDICT: REJECT

ISSUES:
- issue 1
- issue 2

SUGGESTIONS:
- suggestion 1

Rules:
- APPROVE if code is correct, handles errors, and fulfills the task
- REJECT only for real bugs, missing error handling, or code that will definitely crash
- Do NOT reject for style preferences or minor improvements
- Keep feedback concise and actionable — max 5 bullet points total
- If rejecting, be specific about what line or pattern is wrong"""

    def _build_review_prompt(self, code: str, filename: str,
                              past_errors: list[str], goal: str) -> str:
        history_section = ""
        if past_errors:
            history_section = (
                f"\nThis file has failed execution before with these errors:\n"
                + "\n".join(f"- {e[:100]}" for e in past_errors)
                + "\nPay special attention to these failure patterns.\n"
            )

        return (
            f"Task the code was written for: {goal}\n"
            f"File: {filename}\n"
            f"{history_section}\n"
            f"Code to review:\n```python\n{code}\n```"
        )

    def _parse_verdict(self, review_text: str) -> bool:
        """Extract APPROVE/REJECT from review text."""
        upper = review_text.upper()
        if "VERDICT: APPROVE" in upper or "VERDICT:APPROVE" in upper:
            return True
        if "VERDICT: REJECT" in upper or "VERDICT:REJECT" in upper:
            return False
        # If model didn't follow format, default to approve
        # (don't block progress on a confused critic)
        print("[Critic] Couldn't parse verdict — defaulting to APPROVE")
        return True