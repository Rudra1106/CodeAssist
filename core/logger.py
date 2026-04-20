import time
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich import box

console = Console()

# Color scheme per agent — consistent everywhere
AGENT_STYLE = {
    "orchestrator": ("bold white",        "white",     "─"),
    "planner":      ("bold yellow",       "yellow",    "─"),
    "coder":        ("bold cyan",         "cyan",      "─"),
    "critic":       ("bold salmon1",      "salmon1",   "─"),
    "executor":     ("bold green",        "green",     "─"),
    "teacher":      ("bold medium_purple1","medium_purple1","─"),
    "memory":       ("bold grey50",       "grey50",    "─"),
    "system":       ("bold grey46",       "grey46",    "─"),
    "voice":        ("bold magenta",      "magenta",   "─"),
}


def _agent_prefix(agent: str) -> Text:
    bold_style, _, _ = AGENT_STYLE.get(agent, ("bold white", "white", "─"))
    t = Text()
    t.append(f"[{agent.upper()}] ", style=bold_style)
    return t


# ── Basic log lines ────────────────────────────────────────────────────────────

def log(agent: str, message: str):
    """Standard one-liner log."""
    _, color, _ = AGENT_STYLE.get(agent, ("bold white", "white", "─"))
    prefix = _agent_prefix(agent)
    prefix.append(message, style=color)
    console.print(prefix)


def log_dim(agent: str, message: str):
    """Dimmed line for noise-level info (tool args, minor steps)."""
    _, color, _ = AGENT_STYLE.get(agent, ("bold white", "white", "─"))
    prefix = _agent_prefix(agent)
    prefix.append(message, style=f"dim {color}")
    console.print(prefix)


def log_success(agent: str, message: str):
    prefix = _agent_prefix(agent)
    prefix.append("✓ " + message, style="bold green")
    console.print(prefix)


def log_error(agent: str, message: str):
    prefix = _agent_prefix(agent)
    prefix.append("✗ " + message, style="bold red")
    console.print(prefix)


def log_warn(agent: str, message: str):
    prefix = _agent_prefix(agent)
    prefix.append("⚠ " + message, style="bold yellow")
    console.print(prefix)


# ── Thinking / reasoning display ───────────────────────────────────────────────

def log_thinking(agent: str, thought: str):
    """
    Show the model's reasoning chain — the 'thinking out loud' moment.
    Rendered as an indented block so it's visually distinct from actions.
    """
    _, color, _ = AGENT_STYLE.get(agent, ("bold white", "white", "─"))
    console.print()
    console.print(f"  [dim {color}]thinking ↓[/]")
    for line in thought.strip().splitlines():
        console.print(f"  [dim {color}]│[/] [italic dim]{line}[/]")
    console.print(f"  [dim {color}]└─[/]")
    console.print()


def log_plan(steps: list[str]):
    """Render the Planner's output as a numbered step list."""
    console.print()
    console.rule("[bold yellow]PLAN[/]", style="yellow")
    for i, step in enumerate(steps, 1):
        console.print(f"  [bold yellow]{i}.[/] [yellow]{step}[/]")
    console.print()


# ── Tool call display ──────────────────────────────────────────────────────────

def log_tool_call(agent: str, tool_name: str, args: dict):
    """Show what tool is being called and with what arguments."""
    _, color, _ = AGENT_STYLE.get(agent, ("bold white", "white", "─"))

    args_str = "  ".join(
        f"[dim]{k}=[/][{color}]{str(v)[:60]}[/]"
        for k, v in args.items()
    )
    prefix = _agent_prefix(agent)
    prefix.append(f"→ tool: ", style=f"dim {color}")
    prefix.append(tool_name, style=f"bold {color}")
    prefix.append(f"  {args_str}", style="dim")
    console.print(prefix)


def log_tool_result(agent: str, tool_name: str, result: dict):
    """Show whether a tool call succeeded and its key result."""
    success = result.get("success", True)
    if success:
        # Show just the key outcome, not the full dump
        if "content" in result:
            preview = result["content"][:80].replace("\n", " ")
            log_dim(agent, f"← {tool_name}: {preview}...")
        elif "entries" in result:
            names = [e["name"] for e in result.get("entries", [])]
            log_dim(agent, f"← {tool_name}: [{', '.join(names[:6])}]")
        elif "path" in result:
            log_dim(agent, f"← {tool_name}: wrote {result['path']}")
        else:
            log_dim(agent, f"← {tool_name}: ok")
    else:
        log_error(agent, f"← {tool_name}: {result.get('error', 'unknown error')}")


# ── Code display ───────────────────────────────────────────────────────────────

def log_code(agent: str, filename: str, code: str):
    """Syntax-highlighted code block."""
    console.print()
    console.print(f"  [bold cyan]writing → {filename}[/]")
    syntax = Syntax(
        code[:2000],           # cap at 2000 chars to avoid wall of text
        "python",
        theme="monokai",
        line_numbers=True,
        word_wrap=True,
    )
    console.print(syntax)
    if len(code) > 2000:
        console.print(f"  [dim]... ({len(code) - 2000} more chars)[/]")
    console.print()


# ── Critic review display ──────────────────────────────────────────────────────

def log_review(verdict: str, feedback: str):
    """Show critic verdict with color-coded panel."""
    approved = "APPROVE" in verdict.upper()
    style    = "green" if approved else "red"
    icon     = "✓ APPROVED" if approved else "✗ REJECTED"

    console.print()
    console.print(Panel(
        feedback.strip()[:600],
        title=f"[bold {style}]CRITIC: {icon}[/]",
        border_style=style,
        padding=(0, 2),
    ))
    console.print()


# ── Execution output ───────────────────────────────────────────────────────────

def log_execution(success: bool, output: str, error: str = ""):
    """Show sandbox execution result."""
    console.print()
    if success:
        console.rule("[bold green]EXECUTION OUTPUT[/]", style="green")
        console.print(f"[green]{output or '(no output)'}[/]")
    else:
        console.rule("[bold red]EXECUTION ERROR[/]", style="red")
        console.print(f"[red]{error}[/]")
    console.print()


# ── Teacher explanation ────────────────────────────────────────────────────────

def log_explanation(text: str):
    """Render teacher output as a warm styled panel."""
    console.print()
    console.print(Panel(
        text.strip(),
        title="[bold medium_purple1]TEACHER EXPLANATION[/]",
        border_style="medium_purple1",
        padding=(1, 2),
    ))
    console.print()


# ── Session boundaries ─────────────────────────────────────────────────────────

def log_session_start(session_id: str, goal: str, mode: str):
    console.print()
    console.rule("[bold white]ATLAS — Autonomous Coding Assistant[/]")
    table = Table(box=box.SIMPLE, show_header=False, padding=(0,1))
    table.add_column(style="dim")
    table.add_column(style="white")
    table.add_row("session", session_id)
    table.add_row("mode",    f"[cyan]{mode}[/]")
    table.add_row("goal",    goal)
    console.print(table)
    console.rule(style="dim")
    console.print()


def log_session_end(status: str, retries: int, files: list[str]):
    console.print()
    console.rule("[bold white]SESSION SUMMARY[/]")
    color = "green" if status == "success" else "red"
    table = Table(box=box.SIMPLE, show_header=False, padding=(0,1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("status",  f"[{color}]{status}[/]")
    table.add_row("retries", str(retries))
    table.add_row("files",   ", ".join(files) if files else "none")
    console.print(table)
    console.rule(style="dim")
    console.print()


# ── Memory summary ─────────────────────────────────────────────────────────────

def log_memory_loaded(context: str):
    if "No prior memory" in context:
        log("memory", "Fresh start — no prior context.")
        return
    console.print()
    console.print(Panel(
        context.strip(),
        title="[bold grey50]MEMORY LOADED[/]",
        border_style="grey50",
        padding=(0, 2),
    ))
    console.print()


# ── Iteration marker ───────────────────────────────────────────────────────────

def log_iteration(agent: str, n: int):
    _, color, _ = AGENT_STYLE.get(agent, ("bold white","white","─"))
    console.print(f"  [dim {color}]iteration {n}[/]")


def log_retry(attempt: int, max_attempts: int, reason: str):
    console.print()
    console.rule(
        f"[bold yellow]RETRY {attempt}/{max_attempts} — {reason[:60]}[/]",
        style="yellow"
    )
    console.print()