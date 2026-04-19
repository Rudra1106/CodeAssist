import docker
import tempfile
import os
import shutil
from core.state import TaskState


# Safety limits
TIMEOUT_SECONDS = 30
MAX_OUTPUT_BYTES = 50_000   # 50KB cap on stdout/stderr
MEMORY_LIMIT     = "128m"   # container RAM cap
CPU_PERIOD       = 100_000
CPU_QUOTA        = 50_000   # 50% of one core


class Executor:
    """
    Runs code in an isolated Docker container.
    Never touches the host filesystem directly — copies files in,
    runs them, captures output, destroys the container.
    """

    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()  # verify daemon is reachable
            print("[Executor] Docker connected.")
        except Exception as e:
            raise RuntimeError(
                f"[Executor] Cannot connect to Docker: {e}\n"
                "Make sure Docker Desktop is running."
            )

    def run(self, state: TaskState) -> TaskState:
        """
        Find Python files written in this session and run the
        most recently written one in a sandboxed container.
        """
        if not state.files_written:
            state.last_error = "No files to execute."
            print("[Executor] Nothing to run — no files written yet.")
            return state

        # Run the last file written by the Coder
        target = state.files_written[-1]

        # Only execute .py files for now
        if not target.endswith(".py"):
            state.last_error = f"Cannot execute non-Python file: {target}"
            print(f"[Executor] Skipping non-Python file: {target}")
            return state

        print(f"\n[Executor] Running: {target}")
        return self._run_in_container(state, target)

    def _run_in_container(self, state: TaskState, file_path: str) -> TaskState:
        """Copy files to a temp dir, spin up a container, run, capture output."""
        full_path = os.path.abspath(
            os.path.join(state.working_directory, file_path)
            if not os.path.isabs(file_path)
            else file_path
        )

        if not os.path.exists(full_path):
            state.last_error = f"File not found: {full_path}"
            print(f"[Executor] File not found: {full_path}")
            return state

        tmp_dir = tempfile.mkdtemp(prefix="atlas_sandbox_")
        container = None

        try:
            # Copy target file into sandbox dir
            dest_file = os.path.join(tmp_dir, os.path.basename(full_path))
            shutil.copy2(full_path, dest_file)

            # Copy other .py files so imports work
            src_dir = os.path.dirname(full_path)
            for f in os.listdir(src_dir):
                if f.endswith(".py") and f != os.path.basename(full_path):
                    shutil.copy2(os.path.join(src_dir, f), os.path.join(tmp_dir, f))

            print(f"[Executor] Sandbox dir: {tmp_dir}")
            print(f"[Executor] Running: python {os.path.basename(full_path)}")

            # Run detached so we can enforce a timeout manually
            container = self.client.containers.run(
                image="python:3.11-slim",
                command=f"python /sandbox/{os.path.basename(full_path)}",
                volumes={tmp_dir: {"bind": "/sandbox", "mode": "ro"}},
                working_dir="/sandbox",
                mem_limit=MEMORY_LIMIT,
                cpu_period=CPU_PERIOD,
                cpu_quota=CPU_QUOTA,
                network_disabled=True,
                detach=True,            # run in background
                stdout=True,
                stderr=True,
            )

            # Wait with timeout — this is how docker-py handles it properly
            try:
                result = container.wait(timeout=TIMEOUT_SECONDS)
                exit_code = result.get("StatusCode", -1)
            except Exception:
                # Timed out — kill the container
                container.kill()
                state.last_error = f"Execution timed out after {TIMEOUT_SECONDS}s"
                print(f"[Executor] Timed out.")
                return state

            # Capture logs after container finishes
            raw_logs = container.logs(stdout=True, stderr=True)
            output = raw_logs.decode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES]

            if exit_code == 0:
                print(f"[Executor] Success. Output:\n{output or '(no output)'}")
                state.last_output = output
                state.last_error  = ""
                state.add_message("system", f"Execution succeeded:\n{output}", agent="executor")
            else:
                print(f"[Executor] Exited with code {exit_code}:\n{output}")
                state.last_error  = output
                state.last_output = ""
                state.add_message("system", f"Execution failed (exit {exit_code}):\n{output}", agent="executor")

        except docker.errors.APIError as e:
            error = f"Docker API error: {e}"
            print(f"[Executor] {error}")
            state.last_error = error

        except Exception as e:
            error = f"Unexpected executor error: {e}"
            print(f"[Executor] {error}")
            state.last_error = error

        finally:
            # Always clean up — remove container and temp dir
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return state