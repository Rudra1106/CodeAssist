from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TaskState(BaseModel):
    # What the user wants done
    goal: str = ""

    # The plan (list of steps as strings)
    plan: list[str] = Field(default_factory=list)
    current_step: int = 0

    # Files the agents are working with
    working_directory: str = "."
    files_read: list[str] = Field(default_factory=list)
    files_written: list[str] = Field(default_factory=list)

    # Execution results
    last_output: str = ""
    last_error: str = ""
    retry_count: int = 0
    max_retries: int = 3

    # Mode: "learner" shows explanations, "pro" just ships
    mode: str = "learner"
    memory_context: str = ""

    # Session metadata
    session_id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    messages: list[dict] = Field(default_factory=list)

    def add_message(self, role: str, content: str, agent: str = "system"):
        self.messages.append({
            "role": role,
            "content": content,
            "agent": agent,
            "timestamp": datetime.now().isoformat()
        })