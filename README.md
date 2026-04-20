# ATLAS — Autonomous Coding Assistant

> A multi-agent AI system that plans, writes, reviews, executes, and teaches code — with persistent memory and a voice mentor layer. Built entirely with free tools.

---

## Table of Contents

1. [What is ATLAS?](#what-is-atlas)
2. [The Problem It Solves](#the-problem-it-solves)
3. [Architecture Overview](#architecture-overview)
4. [Agent Design](#agent-design)
5. [Project Structure](#project-structure)
6. [File-by-File Explanation](#file-by-file-explanation)
7. [The Self-Correcting Loop](#the-self-correcting-loop)
8. [Memory System](#memory-system)
9. [Voice Layer](#voice-layer)
10. [Terminal UI](#terminal-ui)
11. [Concepts You Learned](#concepts-you-learned)
12. [Free Stack Reference](#free-stack-reference)
13. [Setup & Running](#setup--running)
14. [Future Upgrades](#future-upgrades)

---

## What is ATLAS?

ATLAS is a terminal-based autonomous coding assistant powered by a team of specialized AI agents. Unlike tools like GitHub Copilot or ChatGPT, ATLAS:

- **Remembers you** across sessions using MongoDB
- **Runs and verifies its own code** in a Docker sandbox
- **Self-corrects** when execution fails — no human babysitting
- **Reviews code** before it runs using a Critic agent
- **Teaches you** in plain language after every task using a Teacher agent
- **Speaks to you** like a mentor using free text-to-speech

It is not a chatbot. It is an autonomous agent loop.

---

## The Problem It Solves

| Current tools | ATLAS |
|---|---|
| Stateless — forget you every session | Stateful — remembers your patterns and mistakes |
| Suggest code, you run it manually | Writes code AND runs it in a sandbox |
| One model doing everything | 5 specialized agents, each with one job |
| No feedback loop | Self-corrects on execution failure |
| No teaching | Teacher agent explains every decision |
| Silent | Speaks explanations out loud |

The core insight: **a real mentor doesn't just answer questions — they watch you work, remember your history, and adapt to how you learn.**

---

## Architecture Overview

```
User types a task
       │
       ▼
┌─────────────────────────────────────────────┐
│              ORCHESTRATOR                    │
│  Coordinates all agents, manages retries,   │
│  persists everything to MongoDB              │
└──────┬──────────────────────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│   PLANNER   │────▶│    CODER    │
│ Makes plan  │     │ Writes code │
│ Reads files │     │ Uses tools  │
└─────────────┘     └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   CRITIC    │◀── REJECT (loop back to Coder)
                    │ Reviews diff│
                    └──────┬──────┘
                           │ APPROVE
                           ▼
                    ┌─────────────┐
                    │  EXECUTOR   │
                    │ Docker run  │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │ success                 │ failure
              ▼                         ▼
       ┌─────────────┐        Planner replans
       │   TEACHER   │        Coder rewrites
       │  Explains   │        (up to 3 retries)
       │  + speaks   │
       └─────────────┘
              │
              ▼
         MongoDB memory updated
```

---

## Agent Design

### Orchestrator
The conductor. It does not write code or make plans itself — it sequences the other agents, manages the retry loop, and persists everything to MongoDB. Every run flows through here.

**Key principle:** An orchestrator should be dumb about domain logic and smart about coordination.

### Planner
Uses `list_directory` and `read_file` tools to survey the codebase before producing a numbered plan. On failure, `replan()` is called with the error context injected so it can produce a corrected plan.

**Key principle:** Plan first, code second. Agents that code without a plan produce inconsistent results.

### Coder
The only agent that writes files. Runs in an agentic loop — it keeps calling tools until the model stops issuing tool calls. Uses the OpenAI function-calling format via OpenRouter.

**Key principle:** The agentic loop is just a `while` loop around an LLM call. Keep iterating until `tool_calls` is empty.

### Critic
Reads the file the Coder just wrote and produces a structured APPROVE/REJECT verdict. If rejected, the Orchestrator injects the feedback into the Coder's next run as additional context. Uses a local Ollama model — zero API cost.

**Key principle:** Separate review from generation. A model reviewing its own code catches less than a separate model reviewing it cold.

### Teacher
Active only in `learner` mode. Reads the final approved code, queries MongoDB for the user's mistake history, and generates a personalized explanation. Uses a local Ollama model.

**Key principle:** Personalization requires memory. Without knowing what the user has struggled with, explanations are generic.

### Executor
Copies files to a temp directory, spins up a `python:3.11-slim` Docker container, runs the code, captures stdout/stderr, and destroys the container. Never touches the host environment.

**Key principle:** Never run untrusted code on the host machine. Isolation is non-negotiable.

---

## Project Structure

```
atlas-dev/
├── .env                    # API keys (never commit this)
├── main.py                 # Entry point — launches UI
├── config.py               # Model assignments per agent
├── atlas_memory.db         # (removed after MongoDB migration)
│
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py     # Coordinates the full loop
│   ├── planner.py          # Surveys codebase, makes plan
│   ├── coder.py            # Writes code using file tools
│   ├── critic.py           # Reviews code, approves or rejects
│   └── teacher.py          # Generates personalized explanations
│
├── core/
│   ├── __init__.py
│   ├── state.py            # Shared Pydantic state object
│   ├── llm.py              # Single source of truth for LLM clients
│   ├── memory.py           # MongoDB read/write functions
│   └── voice.py            # Text-to-speech via edge-tts
│
├── tools/
│   ├── __init__.py
│   └── file_tools.py       # read_file, write_file, list_directory + schemas
│
├── sandbox/
│   ├── __init__.py
│   └── executor.py         # Docker sandbox execution
│
├── ui/
│   ├── __init__.py
│   └── app.py              # Textual TUI — 3-panel terminal interface
│
└── test_project/           # Default working directory for the agent
```

---

## File-by-File Explanation

### `core/state.py` — The shared brain

```python
class TaskState(BaseModel):
    goal: str = ""
    plan: list[str] = Field(default_factory=list)
    current_step: int = 0
    working_directory: str = "."
    files_read: list[str] = Field(default_factory=list)
    files_written: list[str] = Field(default_factory=list)
    last_output: str = ""
    last_error: str = ""
    retry_count: int = 0
    max_retries: int = 3
    mode: str = "learner"
    memory_context: str = ""
    session_id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))
    messages: list[dict] = Field(default_factory=list)
```

**Why Pydantic?** Every agent gets this same object. Pydantic validates types automatically, serializes to JSON for MongoDB, and gives you `.model_dump()` for free. This is the pattern used in production ML pipelines everywhere.

**Why a shared state object instead of function arguments?** As systems grow, passing 15 arguments to every function becomes unmaintainable. A single state object that all agents read and write is the standard pattern for multi-agent systems.

---

### `core/llm.py` — Single source of truth for clients

```python
load_dotenv()  # must run before any client is created

def get_client(provider: str) -> OpenAI:
    if provider == "openrouter":
        return OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
    elif provider == "ollama":
        return OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
```

**Why one file?** The 401 error we debugged happened because each agent file had its own `get_client()` copy, and `load_dotenv()` wasn't guaranteed to run before the client was initialized. Centralizing it means the env loads once, correctly, at import time.

**Why does Ollama use the OpenAI SDK?** Ollama exposes an OpenAI-compatible API at port 11434. Same SDK, different base URL. This is the pattern most LLM providers follow now — write once, swap models by changing a string.

---

### `tools/file_tools.py` — What agents can do

```python
FILE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },
    # ... write_file, list_directory
]
```

**What is function calling?** You give the LLM a list of tool schemas in JSON. The model decides when to use them and returns a structured `tool_calls` object instead of text. Your code executes the actual function and feeds the result back. The model never directly runs code — it only requests it.

**Why inject `working_dir` into every tool call?** Agents should be path-agnostic. The working directory is stored in `TaskState` and injected at call time so agents can be reused across projects.

---

### `agents/coder.py` — The agentic loop

```python
for iteration in range(max_iterations):
    response = self.client.chat.completions.create(
        model=self.model,
        messages=messages,
        tools=FILE_TOOLS,
        tool_choice="auto",
    )

    msg = response.choices[0].message
    messages.append(msg.model_dump(exclude_none=True))

    if not msg.tool_calls:
        break  # agent is done

    for tool_call in msg.tool_calls:
        result = run_tool_call(tool_call.function.name, ...)
        messages.append({"role": "tool", "tool_call_id": ..., "content": result})
```

**This is the entire agentic loop pattern.** Every agent framework (LangChain, LlamaIndex, AutoGen) is fundamentally this same while-loop. Understanding it at this level means you can debug any agent system.

**Why `messages.append(msg.model_dump())`?** The LLM has no memory between calls. You must manually maintain the conversation history and send it back every time. The conversation IS the memory, until you add a proper memory layer.

---

### `sandbox/executor.py` — Isolation

```python
result = self.client.containers.run(
    image="python:3.11-slim",
    command=f"python /sandbox/{filename}",
    volumes={tmp_dir: {"bind": "/sandbox", "mode": "ro"}},
    mem_limit="128m",
    network_disabled=True,
    remove=True,          # auto-delete after run
)
```

**Why `mode": "ro"` (read-only)?** The container can read the code but cannot write back to your filesystem. Defense in depth — even if the agent writes malicious code, it cannot escape the sandbox.

**Why `network_disabled=True`?** Generated code should not make network calls. An agent writing `requests.get("https://...")` in your sandbox could exfiltrate data or download malware.

**Why `remove=True`?** Containers accumulate fast. Auto-removal keeps your Docker clean and prevents resource leaks.

---

### `core/memory.py` — MongoDB persistence

```python
def build_memory_context(working_dir: str) -> str:
    """Compact memory string injected into every agent's system prompt."""
    sessions = get_recent_sessions(limit=3)
    ctx      = get_project_context(working_dir)
    patterns = get_user_patterns(limit=6)
    # ... format and return
```

**Why MongoDB over SQLite?** Agent memory is document-shaped. A session has nested fields, messages, variable-length arrays of files. MongoDB stores this natively without schema migrations. SQLite would require you to define columns upfront and join across tables.

**Why `$setOnInsert` with upsert?** For patterns and project context, you want to update if the key exists and insert if it doesn't — in one atomic operation. `upsert=True` + `$setOnInsert` for new fields + `$set` for updated fields is the standard MongoDB upsert pattern.

**What is `build_memory_context`?** It compiles everything the agents need to know about you into a single string that gets injected into system prompts. This is how you turn a stateless LLM into a stateful assistant without fine-tuning.

---

### `agents/critic.py` — Structured output parsing

```python
def _parse_verdict(self, review_text: str) -> bool:
    upper = review_text.upper()
    if "VERDICT: APPROVE" in upper:
        return True
    if "VERDICT: REJECT" in upper:
        return False
    return True  # default to approve if format not followed
```

**Why default to APPROVE on parse failure?** The Critic's job is to catch real bugs, not block progress. If the model produces a confused response, it's safer to let execution proceed and let the Executor catch real errors than to block indefinitely on a confused reviewer.

**Why a separate model for the Critic?** The Coder is already committed to its output — it generated the code and believes it's correct. A separate model reviewing it cold has no attachment to the output and catches different classes of errors.

---

### `core/voice.py` — Free TTS

```python
communicate = edge_tts.Communicate(text, "en-US-GuyNeural", rate="+5%")
await communicate.save(tmp.name)
subprocess.run(["afplay", tmp.name])  # macOS built-in player
```

**Why `edge-tts`?** It uses Microsoft Edge's neural TTS engine — the same voices as the Edge browser. 300+ voices, natural prosody, completely free, no API key. The audio quality is far above `pyttsx3` or `espeak`.

**Why run in a thread?** TTS takes 200–500ms to generate and play. If you call it synchronously, the entire UI freezes. Running it in a daemon thread lets the UI stay responsive while audio plays in the background.

---

## The Self-Correcting Loop

This is the most important concept in the project. A human coding manually does this loop in their head:

```
Write code → run it → see error → understand error → fix code → run again
```

ATLAS does the same thing autonomously:

```python
# agents/orchestrator.py
state = self.executor.run(state)

while state.last_error and state.retry_count < state.max_retries:
    state.retry_count += 1

    # Planner reads the error and adjusts the plan
    state = self.planner.replan(state)

    # Coder writes a new version with the error context
    state = self.coder.run(state)

    # Critic reviews the new version
    state = self._critic_loop(state)

    # Executor verifies again
    state = self.executor.run(state)
```

The key is that `state.last_error` contains the real stderr output from Docker. The Planner's `replan()` injects this error directly into the prompt so the model sees exactly what went wrong. This is not magic — it is just structured error feedback.

---

## Memory System

ATLAS stores five types of memory in MongoDB:

| Collection | What it stores | Used for |
|---|---|---|
| `sessions` | Every run: goal, status, files, retries | Recent session context |
| `messages` | Every agent message in every session | Debugging, audit trail |
| `project_context` | Files written, tech stack, decisions per directory | Project awareness |
| `user_patterns` | Mistakes made, skills learned, counts | Personalizing the Teacher |
| `execution_history` | Per-file run results: success, error, output | Critic's past failure awareness |

The `build_memory_context()` function assembles a compact summary injected into every agent's system prompt. This is how a stateless LLM call becomes "aware" of your history — the context IS the memory.

**View your memory live in MongoDB Compass:**
- Connect to `mongodb://localhost:27017`
- Open database `atlas_dev`
- Collections update in real time as agents run

---

## Voice Layer

ATLAS uses `edge-tts` for free, high-quality voice output. The Teacher agent's explanation is spoken aloud after every successful task.

**Setup:**
```bash
pip install edge-tts
```

**Available voices (change in `core/voice.py`):**
- `en-US-GuyNeural` — warm male mentor (default)
- `en-US-JennyNeural` — professional female
- `en-IN-NeerjaNeural` — Indian English female
- `en-GB-RyanNeural` — British male

**Keyboard controls in the UI:**
- `v` — toggle voice on/off
- `e` — replay last Teacher explanation

**File watching (planned for v2):** The `watchdog` library can monitor your project folder. On every file save, a background Critic agent reads the diff and speaks feedback automatically — like a mentor looking over your shoulder.

---

## Terminal UI

Built with [Textual](https://textual.textualize.io/) — a Python TUI framework.

**Three panels:**

| Panel | Content |
|---|---|
| Left | Project file tree, session ID, retry counter |
| Center | Live agent stream, color-coded by agent |
| Right | MongoDB memory inspector — sessions, patterns, context |

**Color coding:**
- Yellow = Planner
- Cyan = Coder
- Salmon = Critic
- Green = Executor
- Purple = Teacher
- White/dim = Orchestrator/System

**Keyboard shortcuts:**

| Key | Action |
|---|---|
| `Enter` | Submit task from input bar |
| `v` | Toggle voice |
| `m` | Refresh memory panel |
| `e` | Replay last explanation |
| `q` | Quit |

---

## Concepts You Learned

### 1. Agentic loops
The fundamental pattern of every AI agent system: call LLM → check for tool calls → execute tools → feed results back → repeat until no tool calls. No framework required. Just a while loop.

### 2. Function calling / tool use
Giving an LLM a JSON schema of available functions. The model decides when and how to call them — you execute the actual code. Separates "what to do" (model) from "how to do it" (your code).

### 3. Shared state with Pydantic
Using a single typed state object that all agents read and write instead of passing arguments between functions. Standard in production ML pipelines.

### 4. Multi-agent specialization
Why one LLM doing everything produces worse results than 5 specialized agents. Separation of concerns applies to AI systems just as it does to software architecture.

### 5. Docker sandboxing
Running untrusted generated code in an isolated container with no network access, read-only mounts, memory limits, and automatic cleanup. The non-negotiable safety pattern for code execution.

### 6. OpenAI-compatible APIs
How OpenRouter, Ollama, and the OpenAI API all speak the same protocol. Write one client, change a base URL string to switch between providers. This is now the industry standard.

### 7. MongoDB document modeling
Modeling agent memory as flexible documents instead of fixed SQL rows. Why document databases fit agent state better than relational databases.

### 8. Fallback patterns
Designing systems that degrade gracefully. Primary model fails → fallback to local model. Critic confused → default to approve. Every production AI system needs explicit fallback logic.

### 9. Prompt injection for statefulness
How to make a stateless LLM "remember" — inject a compact memory summary into every system prompt. The model's context window IS its working memory.

### 10. Structured output parsing
Getting reliable structured data from an LLM by specifying an exact format in the system prompt and parsing it defensively (defaulting safely when the format isn't followed).

### 11. Threading for non-blocking UIs
Running blocking LLM calls in background threads so the UI stays responsive. Using `call_from_thread()` to safely update UI state from background threads.

### 12. Environment variable hygiene
Why `load_dotenv()` must run before any client is initialized. Why centralizing configuration in one file prevents subtle bugs. Why `.env` must never be committed.

---

## Free Stack Reference

| Component | Tool | Cost | Why |
|---|---|---|---|
| Planning / Orchestration | `google/gemini-2.0-flash-exp:free` via OpenRouter | Free | Large context, strong reasoning |
| Code generation | `openai/gpt-4o-mini` via OpenRouter | ~$0.002/run | Reliable tool use support |
| Code review (Critic) | `qwen2.5-coder:3b` via Ollama | Free (local) | Runs on-device, zero API cost |
| Teaching (Teacher) | `deepseek-r1:1.5b` via Ollama | Free (local) | Good at explanation tasks |
| Code execution | Docker `python:3.11-slim` | Free (local) | Isolated sandbox |
| Memory | MongoDB local | Free | Document-native, Compass UI |
| Text-to-speech | `edge-tts` | Free | Neural quality, 300+ voices |
| Terminal UI | Textual | Free | Python-native, production quality |

---

## Setup & Running

### Prerequisites
- Python 3.11+
- Docker Desktop running
- Ollama installed and running
- MongoDB running locally (port 27017)

### Install
```bash
git clone <your-repo>
cd atlas-dev
python3 -m venv venv
source venv/bin/activate
pip install openai pydantic python-dotenv watchdog textual docker rich pymongo edge-tts
```

### Pull local models
```bash
ollama pull qwen2.5-coder:3b
ollama pull deepseek-r1:1.5b
```

### Configure
Create `.env` in the project root:
```env
OPENROUTER_API_KEY=your_openrouter_key_here
OLLAMA_BASE_URL=http://localhost:11434
MONGO_URI=mongodb://localhost:27017
```

### Run
```bash
# Launch the terminal UI
python main.py

# Or target a specific project directory
python main.py ./my_project
```

### Example tasks to try
```
Create a file called api_client.py with a class that wraps the requests library, handles retries, and logs all calls

Create a file called data_validator.py with functions to validate email addresses, phone numbers, and dates

Create a file called file_organizer.py that sorts files in a directory into subdirectories by extension
```

---

## Future Upgrades

### Intelligence upgrades

**RAG over your codebase**
Embed every file in your project using a local embedding model (nomic-embed-text via Ollama) and store vectors in Qdrant (free local). The Planner can semantically search for relevant code before planning instead of just listing files. Scales to large codebases.

**Skill memory**
Store successful code patterns as reusable "skills" in MongoDB. When the Planner sees a similar task, it retrieves relevant past solutions and injects them as examples. The system gets better the more you use it.

**Test generation agent**
Add a Tester agent between the Critic and Executor. It generates pytest tests for the code the Coder wrote, runs them in the sandbox, and fails back to the Coder if tests don't pass. Forces the system to write testable code.

**Live file watcher**
Activate the `watchdog` integration so the Critic silently reviews every file you save in your editor. The Teacher speaks a one-sentence observation when something interesting is detected. Passive mentorship with no task required.

**Multi-file planning**
Upgrade the Planner to reason about file dependencies and produce DAG-style plans where multiple files can be written in parallel. The Orchestrator runs independent steps concurrently using `asyncio.gather`.

### UX upgrades

**VS Code extension**
Wrap the Python backend in a FastAPI server and build a VS Code extension that calls it. Same agents, same memory, sidebar panel instead of terminal. The backend is already clean enough to expose as an API.

**Conversation mode**
Add a Dialogue agent that can answer questions about the code it just wrote, explain specific lines, or discuss architectural choices — using the session's message history as context.

**Cost tracker**
Log token counts and estimated cost per agent call to MongoDB. Surface a daily spend in the UI status bar. Critical for production use when you move off free tiers.

**Diff viewer**
Show a syntax-highlighted diff of what changed in each file the Coder writes. Makes it easy to see exactly what the agent modified without opening the file.

### Robustness upgrades

**Streaming output**
Use `stream=True` in LLM calls and stream tokens into the UI panel in real time instead of waiting for the full response. Dramatically improves perceived responsiveness.

**Timeout enforcement**
Implement proper async timeouts on Docker execution using `asyncio.wait_for`. Kill containers that exceed 30 seconds instead of relying on Docker's own timeout which varies by version.

**Agent observability**
Add OpenTelemetry tracing so every agent call, tool use, and retry is logged with timestamps and token counts. Makes debugging production failures trivial.

**Self-hosted models**
Replace OpenRouter with a local Ollama model for all agents when you have a machine with enough VRAM. `qwen2.5-coder:32b` or `deepseek-coder-v2:16b` via Ollama can match GPT-4o-mini on coding tasks at zero ongoing cost.

---

## What to Build Next

Now that you understand this system end-to-end, the **Personal AI Research Assistant** is the natural next project. Here is why it will feel familiar:

| ATLAS concept | Research Assistant equivalent |
|---|---|
| Coder agent writing files | Ingestion agent chunking and embedding documents |
| File tools (`read_file`) | Retrieval tools (`semantic_search`, `fetch_document`) |
| MongoDB session memory | Conversation history + note memory |
| Docker sandbox | No sandbox needed (read-only research) |
| Critic reviewing code | Fact-checker agent reviewing answers |
| TaskState shared object | Same pattern, different fields |

The new concepts you will add: vector embeddings, cosine similarity search, chunking strategies, and Qdrant (free local vector database). Everything else you have already built.

---

*Built with Python 3.11 · OpenRouter · Ollama · Docker · MongoDB · Textual · edge-tts*
