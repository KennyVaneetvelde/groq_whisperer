# Replace logging imports with loguru
import os
import tempfile
import wave
from datetime import datetime
from pathlib import Path

import keyboard
import pyaudio
import pyautogui
import pyperclip
from groq import Groq
from loguru import logger
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel

# Replace logging setup with loguru configuration
log_path = Path(__file__).parent / "logs"
log_path.mkdir(parents=True, exist_ok=True)
log_file = log_path / (f'groq_whisperer_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

# Configure loguru
logger.remove()  # Remove default handler
logger.add(
    log_file,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    level="DEBUG",
    rotation="1 day",
    retention="7 days",
    enqueue=True,
)
logger.add(lambda msg: console.print(f"[dim]{msg}[/dim]"), level="DEBUG")

# Initialize rich console
console = Console()

# Set up Groq client
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    msg = "[red]Error:[/red] Please set the GROQ_API_KEY environment variable"
    console.print(msg)
    raise ValueError("Please set the GROQ_API_KEY environment variable")
client = Groq(api_key=api_key)


def record_audio(sample_rate=16000, channels=1, chunk=1024):
    """Record audio from the microphone while the alt+x button is held down."""
    logger.debug("Initializing audio recording")
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=channels,
        rate=sample_rate,
        input=True,
        frames_per_buffer=chunk,
    )

    msg = "[yellow]Press and hold the alt+x button to start recording...[/yellow]"
    console.print(Panel.fit(msg))
    frames = []

    keyboard.wait("alt+x")
    logger.info("Recording started")
    console.print("[green]Recording...[/green] (Release alt+x to stop)")

    while keyboard.is_pressed("alt+x"):
        try:
            data = stream.read(chunk)
            frames.append(data)
        except Exception as e:
            logger.error(f"Error during recording: {e}")
            raise

    logger.info("Recording finished")
    console.print("[blue]Recording finished.[/blue]")
    stream.stop_stream()
    stream.close()
    p.terminate()

    return frames, sample_rate


def save_audio(frames, sample_rate):
    """Save recorded audio to a temporary WAV file."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        wf = wave.open(temp_audio.name, "wb")
        wf.setnchannels(1)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(pyaudio.paInt16))
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))
        wf.close()
        return temp_audio.name


def transcribe_audio(audio_file_path):
    """Transcribe audio using Groq's Whisper API."""
    try:
        logger.debug(f"Starting transcription of file: {audio_file_path}")
        with open(audio_file_path, "rb") as file:
            logger.debug("Sending request to Groq API")

            # Use audio transcriptions endpoint instead of chat
            transcription = client.audio.transcriptions.create(
                file=file,  # Send file directly
                model="whisper-large-v3",
                prompt=(
                    "The audio is by a programmer discussing programming "
                    "issues, the programmer mostly uses python and might "
                    "mention python libraries or reference code in his speech."
                ),
                response_format="text",
                language="en",
            )

            logger.info(f"Transcription received: {transcription[:50]}...")
            return transcription

    except Exception as e:
        logger.error("Transcription error", exception=e)
        return None


def copy_transcription_to_clipboard(text):
    """Copy the transcribed text to clipboard using pyperclip."""
    pyperclip.copy(text)
    pyautogui.hotkey("alt+z")


def main():
    """Main application function."""
    logger.info("Starting Groq Whisperer")
    title = "[cyan]Groq Whisperer[/cyan]\n[dim]Voice transcription powered by Groq[/dim]"
    console.print(Panel.fit(title, border_style="cyan"))

    # Create layout
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3), Layout(name="body"), Layout(name="status", size=3), Layout(name="footer", size=3)
    )

    # Initialize layout with content
    layout["header"].update(Align.center("[bold cyan]Groq Whisperer[/bold cyan]"))
    layout["body"].update(Panel("[dim]Waiting for recording...[/dim]", border_style="blue", title="Transcription"))
    layout["status"].update(Align.center("[dim]Ready[/dim]"))
    layout["footer"].update(Align.center("[yellow]Press alt+x to start recording[/yellow]"))

    try:
        # Use screen=True to properly render the layout
        with Live(layout, refresh_per_second=4, screen=True) as live:
            while True:
                try:
                    frames, sample_rate = record_audio()
                    logger.debug(f"Audio recorded: {len(frames)} frames at {sample_rate}Hz")

                    layout["status"].update(Align.center("[yellow]Saving audio...[/yellow]"))
                    live.refresh()

                    temp_audio_file = save_audio(frames, sample_rate)
                    logger.debug(f"Audio saved to: {temp_audio_file}")

                    try:
                        layout["status"].update(Align.center("[yellow]Transcribing audio...[/yellow]"))
                        live.refresh()

                        transcription = transcribe_audio(temp_audio_file)

                        if transcription:
                            logger.success("Transcription successful")
                            layout["body"].update(Panel(transcription, border_style="green", title="Transcription"))
                            layout["status"].update(Align.center("[green]Transcription successful[/green]"))
                            live.refresh()
                            copy_transcription_to_clipboard(transcription)
                            logger.debug("Transcription copied to clipboard")
                        else:
                            logger.error("Transcription failed")
                            layout["body"].update(
                                Panel(
                                    "[red]Transcription failed - API may not support audio[/red]",
                                    border_style="red",
                                    title="Error",
                                )
                            )
                            layout["status"].update(Align.center("[red]Transcription failed[/red]"))
                            live.refresh()
                    finally:
                        if os.path.exists(temp_audio_file):
                            os.unlink(temp_audio_file)
                            logger.debug(f"Cleaned up temporary file: {temp_audio_file}")

                        layout["footer"].update(Align.center("[yellow]Press alt+x to start recording[/yellow]"))
                        layout["status"].update(Align.center("[dim]Ready[/dim]"))
                        live.refresh()

                except Exception as e:
                    logger.exception("Error in main loop")
                    layout["body"].update(Panel(f"[red]Error: {str(e)}[/red]", border_style="red", title="Error"))
                    live.refresh()

    except KeyboardInterrupt:
        logger.info("Application terminated by user")
        console.print("\n[yellow]Application terminated by user[/yellow]")
    except Exception as e:
        logger.exception("Fatal error occurred")
        console.print(f"\n[red]An unexpected error occurred: {str(e)}[/red]")


if __name__ == "__main__":
    main()
