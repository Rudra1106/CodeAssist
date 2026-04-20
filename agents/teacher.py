from core.llm import get_client
from core.state import TaskState
from core.memory import get_user_patterns, record_pattern
from core.logger import log, log_error, log_explanation
from config import MODELS
from tools.file_tools import read_file


class TeacherAgent:
    """
    Active only in learner mode.
    Reads the final approved code + critic feedback and generates
    a personalized explanation based on the user's memory profile.
    Uses a local Ollama model — free, always available.
    """

    def __init__(self):
        cfg = MODELS["teacher"]
        self.provider = cfg["provider"]
        self.model    = cfg["model"]
        self.client   = get_client(self.provider)

    def explain(self, state: TaskState, critic_feedback: str = "") -> TaskState:
        """Generate a teaching explanation for the code that was just written."""
        if state.mode != "learner":
            return state

        if not state.files_written:
            return state

        target = state.files_written[-1]
        log("teacher", f"Generating explanation for: {target} — model: {self.model}")

        # Read the code
        result = read_file(target, working_dir=state.working_directory)
        if not result["success"]:
            return state

        code = result["content"]

        # Pull user's pattern history to personalize the explanation
        mistakes  = get_user_patterns(category="mistake",  limit=3)
        skills    = get_user_patterns(category="skill",    limit=3)

        prompt = self._build_prompt(code, target, state.goal,
                                    mistakes, skills, critic_feedback)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user",   "content": prompt}
                ],
                max_tokens=1500,
            )
            explanation = response.choices[0].message.content or ""
        except Exception as e:
            print(f"[Teacher] Model error: {e}")
            return state

        log_explanation(explanation)
        state.add_message("assistant", explanation, agent="teacher")
        record_pattern(f"Learned: {state.goal[:60]}", category="skill")
        return state

    def _system_prompt(self) -> str:
        return """You are a patient, encouraging coding mentor.

Your job is to explain code clearly to someone who is learning.

Style:
- Use simple language, avoid jargon unless you explain it
- Reference what the user has struggled with before (if provided)
- Point out the most important concept in the code — not everything
- End with ONE actionable next step the learner could try themselves
- Keep it under 200 words — quality over quantity
- Be warm and specific, not generic"""

    def _build_prompt(self, code: str, filename: str, goal: str,
                      mistakes: list[dict], skills: list[dict],
                      critic_feedback: str) -> str:

        mistakes_text = ""
        if mistakes:
            mistakes_text = (
                "\nThis learner has struggled with:\n"
                + "\n".join(f"- {m['pattern']}" for m in mistakes)
            )

        skills_text = ""
        if skills:
            skills_text = (
                "\nThey've successfully learned:\n"
                + "\n".join(f"- {s['pattern']}" for s in skills)
            )

        critic_text = ""
        if critic_feedback and "APPROVE" in critic_feedback.upper():
            # Extract suggestions even from approved reviews
            if "SUGGESTIONS:" in critic_feedback:
                critic_text = (
                    "\nThe code reviewer noted these suggestions:\n"
                    + critic_feedback.split("SUGGESTIONS:")[-1].strip()[:300]
                )

        return (
            f"The learner just completed this task: {goal}\n"
            f"File written: {filename}\n"
            f"{mistakes_text}"
            f"{skills_text}"
            f"{critic_text}\n\n"
            f"Code written:\n```python\n{code}\n```\n\n"
            f"Write a personalized explanation for this learner."
        )