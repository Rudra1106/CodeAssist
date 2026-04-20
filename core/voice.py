import asyncio
import os
import tempfile
import threading
import subprocess
from typing import Optional


# Voice settings — change VOICE to any edge-tts voice name
VOICE   = "en-US-GuyNeural"       # warm male mentor voice
RATE    = "+5%"                    # slightly faster than default
VOLUME  = "+0%"


def speak(text: str, blocking: bool = False):
    """
    Speak text using edge-tts (free, no API key).
    blocking=False plays in background so UI doesn't freeze.
    """
    # Strip markdown formatting — TTS sounds bad reading "**bold**"
    clean = _strip_markdown(text)
    if not clean.strip():
        return

    if blocking:
        asyncio.run(_speak_async(clean))
    else:
        thread = threading.Thread(target=asyncio.run, args=(_speak_async(clean),), daemon=True)
        thread.start()


async def _speak_async(text: str):
    """Generate speech and play it."""
    try:
        import edge_tts
        # Write to a temp mp3 file
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()

        communicate = edge_tts.Communicate(text, VOICE, rate=RATE, volume=VOLUME)
        await communicate.save(tmp.name)

        # Play using macOS afplay (built-in, zero install)
        subprocess.run(
            ["afplay", tmp.name],
            check=True,
            capture_output=True
        )
    except Exception as e:
        print(f"[Voice] Error: {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _strip_markdown(text: str) -> str:
    """Remove markdown so TTS reads naturally."""
    import re
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)   # **bold**
    text = re.sub(r'\*(.+?)\*',     r'\1', text)   # *italic*
    text = re.sub(r'`(.+?)`',       r'\1', text)   # `code`
    text = re.sub(r'#+\s',          '',    text)   # ## headers
    text = re.sub(r'^\s*[-*]\s',    '',    text, flags=re.MULTILINE)  # bullets
    return text.strip()