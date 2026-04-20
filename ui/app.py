import asyncio
import threading
import queue
from datetime import datetime
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Header, Footer, Static, Label,
    Input, RichLog, Tree, Switch
)
from textual.reactive import reactive
from textual.binding import Binding
from rich.text import Text
from rich.panel import Panel

from core.state import TaskState
from core.memory import init_db, get_recent_sessions, get_user_patterns, get_project_context
from agents.orchestrator import Orchestrator
from core.voice import speak


# Colour map per agent — matches our mockup
AGENT_COLORS = {
    "orchestrator": "dim white",
    "planner":      "yellow",
    "coder":        "cyan",
    "critic":       "salmon1",
    "executor":     "green",
    "teacher":      "medium_purple1",
    "memory":       "grey50",
    "system":       "grey46",
}


class AgentStream(RichLog):
    """Center panel — streams agent output lines with color coding."""

    def log_agent(self, agent: str, message: str):
        color = AGENT_COLORS.get(agent, "white")
        tag   = f"[{agent.upper()}]"
        line  = Text()
        line.append(f"{tag:<16}", style=f"bold {color}")
        line.append(message, style=color)
        self.write(line)


class MemoryPanel(Static):
    """Right panel — shows live MongoDB memory state."""

    def compose(self) -> ComposeResult:
        yield Label("MEMORY INSPECTOR", id="mem-title")
        yield ScrollableContainer(Static("Loading...", id="mem-content"))

    def refresh_memory(self, working_dir: str):
        sessions = get_recent_sessions(limit=3)
        patterns = get_user_patterns(limit=6)
        ctx      = get_project_context(working_dir)

        lines = []

        lines.append("[yellow]RECENT SESSIONS[/]")
        if sessions:
            for s in sessions:
                status_color = "green" if s["status"] == "success" else "red"
                lines.append(
                    f"[dim]{s['created_at'][5:10]}[/] "
                    f"[{status_color}]{s['status'][:4]}[/] "
                    f"[white]{s['goal'][:22]}[/]"
                )
        else:
            lines.append("[dim]No sessions yet[/]")

        lines.append("")
        lines.append("[yellow]PROJECT CONTEXT[/]")
        if ctx:
            for k, v in list(ctx.items())[:4]:
                lines.append(f"[dim]{k[:14]}[/]\n[cyan]{v[:20]}[/]")
        else:
            lines.append("[dim]No context yet[/]")

        lines.append("")
        lines.append("[yellow]USER PATTERNS[/]")
        if patterns:
            for p in patterns:
                cat_color = "red" if p["category"] == "mistake" else "green"
                lines.append(
                    f"[{cat_color}]{p['category'][:7]}[/] "
                    f"[dim]×{p['count']}[/] "
                    f"[white]{p['pattern'][:20]}[/]"
                )
        else:
            lines.append("[dim]No patterns yet[/]")

        content = "\n".join(lines)
        self.query_one("#mem-content", Static).update(content)


class FilePanel(Static):
    """Left panel — project file tree and session status."""

    def compose(self) -> ComposeResult:
        yield Label("PROJECT FILES", id="file-title")
        yield Tree("./", id="file-tree")
        yield Label("", id="session-status")

    def refresh_files(self, working_dir: str, session_id: str, retries: int, max_retries: int):
        import os
        tree = self.query_one("#file-tree", Tree)
        tree.clear()
        root = tree.root

        try:
            for entry in sorted(os.scandir(working_dir), key=lambda e: e.name):
                if entry.name.startswith("."):
                    continue
                label = f"[green]{entry.name}[/]" if entry.is_file() else f"[yellow]{entry.name}/[/]"
                root.add_leaf(label)
        except Exception:
            root.add_leaf("[dim]no files yet[/]")

        root.expand()

        status = (
            f"[dim]session[/]\n{session_id[-8:]}\n\n"
            f"[dim]retries[/]\n"
            f"{'[green]' if retries == 0 else '[yellow]'}{retries}/{max_retries}[/]"
        )
        self.query_one("#session-status", Label).update(status)


class AtlasApp(App):
    """The main ATLAS terminal UI."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #main-layout {
        layout: horizontal;
        height: 1fr;
    }
    #left-panel {
        width: 22;
        border-right: solid $surface;
        padding: 0 1;
    }
    #center-panel {
        width: 1fr;
        padding: 0 1;
    }
    #right-panel {
        width: 28;
        border-left: solid $surface;
        padding: 0 1;
    }
    #input-row {
        height: 5;
        padding: 1 1;
        border-top: solid $surface;
    }
    #task-input {
        width: 1fr;
    }
    #file-title, #mem-title {
        color: $text-muted;
        text-style: bold;
        padding-bottom: 1;
    }
    #voice-switch-row {
        layout: horizontal;
        height: 3;
        align: left middle;
        padding: 0 1;
    }
    AgentStream {
        height: 1fr;
        border: none;
    }
    """

    BINDINGS = [
        Binding("q",     "quit",         "Quit"),
        Binding("ctrl+r","run_task",      "Run"),
        Binding("m",     "refresh_mem",   "Memory"),
        Binding("e",     "explain_last",  "Explain"),
        Binding("v",     "toggle_voice",  "Voice"),
    ]

    voice_enabled: reactive[bool] = reactive(True)

    def __init__(self, working_dir: str = "./test_project"):
        super().__init__()
        self.working_dir  = working_dir
        self.task_queue   = queue.Queue()
        self.current_state: TaskState | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-layout"):
            with Vertical(id="left-panel"):
                yield FilePanel(id="file-panel")
            with Vertical(id="center-panel"):
                yield AgentStream(id="agent-stream", highlight=True, markup=True)
            with Vertical(id="right-panel"):
                yield MemoryPanel(id="mem-panel")
        with Horizontal(id="input-row"):
            yield Input(
                placeholder="Describe a coding task and press Enter...",
                id="task-input"
            )
        yield Footer()

    def on_mount(self):
        import os
        os.makedirs(self.working_dir, exist_ok=True)
        init_db()
        stream = self.query_one("#agent-stream", AgentStream)
        stream.log_agent("system", "ATLAS ready. Type a task and press Enter.")
        stream.log_agent("memory", f"Working dir: {self.working_dir}")
        self.refresh_panels()

    def on_input_submitted(self, event: Input.Submitted):
        task = event.value.strip()
        if not task:
            return
        event.input.value = ""
        self.run_task_with(task)

    def run_task_with(self, goal: str):
        stream = self.query_one("#agent-stream", AgentStream)
        stream.log_agent("orchestrator", f"Starting: {goal[:60]}")

        state = TaskState(
            goal=goal,
            working_directory=self.working_dir,
            mode="learner",
            max_retries=3,
        )
        self.current_state = state

        # Run the orchestrator in a background thread
        # so the UI stays responsive
        def run():
            # Monkey-patch print to stream into UI
            import builtins
            original_print = builtins.print

            def ui_print(*args, **kwargs):
                text = " ".join(str(a) for a in args)
                self._parse_and_stream(text)
                original_print(*args, **kwargs)

            builtins.print = ui_print

            try:
                orch  = Orchestrator()
                final = orch.run(state)
                self.current_state = final

                # Speak teacher explanation if voice on
                if self.voice_enabled and final.messages:
                    teacher_msgs = [
                        m["content"] for m in final.messages
                        if m.get("agent") == "teacher"
                    ]
                    if teacher_msgs:
                        speak(teacher_msgs[-1])

                self.call_from_thread(self.refresh_panels)

            except Exception as e:
                self.call_from_thread(
                    stream.log_agent, "system", f"Error: {e}"
                )
            finally:
                builtins.print = original_print

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _parse_and_stream(self, text: str):
        """Route print output to the right agent color in the stream."""
        stream = self.query_one("#agent-stream", AgentStream)
        agent  = "system"

        lower = text.lower()
        if "[planner]"      in lower: agent = "planner"
        elif "[coder]"      in lower: agent = "coder"
        elif "[critic]"     in lower: agent = "critic"
        elif "[executor]"   in lower: agent = "executor"
        elif "[teacher]"    in lower: agent = "teacher"
        elif "[memory]"     in lower: agent = "memory"
        elif "[orchestrator]" in lower: agent = "orchestrator"

        # Strip the tag prefix so it's not shown twice
        for tag in ["[Planner]","[Coder]","[Critic]","[Executor]",
                    "[Teacher]","[Memory]","[Orchestrator]","[Executor]"]:
            text = text.replace(tag, "").replace(tag.lower(), "")

        self.call_from_thread(stream.log_agent, agent, text.strip())

    def refresh_panels(self):
        state = self.current_state
        session_id  = state.session_id  if state else "—"
        retries     = state.retry_count if state else 0
        max_retries = state.max_retries if state else 3

        self.query_one("#file-panel",  FilePanel).refresh_files(
            self.working_dir, session_id, retries, max_retries
        )
        self.query_one("#mem-panel", MemoryPanel).refresh_memory(self.working_dir)

    def action_refresh_mem(self):
        self.query_one("#mem-panel", MemoryPanel).refresh_memory(self.working_dir)

    def action_toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        status = "ON" if self.voice_enabled else "OFF"
        stream = self.query_one("#agent-stream", AgentStream)
        stream.log_agent("system", f"Voice {status}")
        speak(f"Voice {status}") if self.voice_enabled else None

    def action_explain_last(self):
        """Re-speak the last teacher explanation."""
        if not self.current_state:
            return
        teacher_msgs = [
            m["content"] for m in self.current_state.messages
            if m.get("agent") == "teacher"
        ]
        if teacher_msgs and self.voice_enabled:
            speak(teacher_msgs[-1])
        elif teacher_msgs:
            stream = self.query_one("#agent-stream", AgentStream)
            stream.log_agent("teacher", teacher_msgs[-1])