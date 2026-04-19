import json
from typing import Any, Dict, Union


def read_json_file(file_path: str) -> Union[Dict[str, Any], str]:
    """Reads a JSON file and returns its content as a dictionary.

    Args:
        file_path (str): Path to the JSON file.

    Returns:
        Union[Dict[str, Any], str]: Content of the JSON file as a dictionary or an error message.
    """
    try:
        with open(file_path, 'r') as json_file:
            return json.load(json_file)
    except FileNotFoundError:
        return f"Error: The file {file_path} was not found."
    except json.JSONDecodeError:
        return "Error: Failed to decode JSON from the file."
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"
