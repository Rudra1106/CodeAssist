import os


def read_file(path: str, working_dir: str = ".") -> dict:
    """Read a file and return its contents."""
    full_path = os.path.join(working_dir, path)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"success": True, "content": content, "path": full_path}
    except FileNotFoundError:
        return {"success": False, "error": f"File not found: {full_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str, working_dir: str = ".") -> dict:
    """Write content to a file, creating directories if needed."""
    full_path = os.path.join(working_dir, path)
    try:
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "path": full_path, "bytes_written": len(content)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_directory(path: str = ".", working_dir: str = ".") -> dict:
    """List files in a directory."""
    full_path = os.path.join(working_dir, path)
    try:
        entries = []
        for entry in os.scandir(full_path):
            entries.append({
                "name": entry.name,
                "type": "file" if entry.is_file() else "dir",
                "size": entry.stat().st_size if entry.is_file() else None
            })
        return {"success": True, "entries": entries, "path": full_path}
    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool definitions in OpenAI function-calling format
# Both OpenRouter and Ollama understand this format
FILE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating it if it doesn't exist",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "content": {"type": "string", "description": "Full content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List all files and folders in a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path, defaults to current"}
                },
                "required": []
            }
        }
    }
]