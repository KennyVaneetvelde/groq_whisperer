import os
import tempfile
import wave

import keyboard
import pyaudio
import pyautogui
import pyperclip
from groq import Groq
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

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
    console.print("[green]Recording...[/green] (Release alt+x to stop)")

    while keyboard.is_pressed("alt+x"):
        data = stream.read(chunk)
        frames.append(data)

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
    """Transcribe audio using Groq's Whisper implementation."""
    try:
        with open(audio_file_path, "rb") as file:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = "Transcribing audio..."
                progress.add_task(description=task, total=None)
                transcription = client.audio.transcriptions.create(
                    file=(os.path.basename(audio_file_path), file.read()),
                    model="whisper-large-v3",
                    prompt=(
                        "The audio is by a programmer discussing programming "
                        "issues, the programmer mostly uses python and might "
                        "mention python libraries or reference code in his speech."
                    ),
                    response_format="text",
                    language="en",
                )
        return transcription
    except Exception as e:
        console.print(f"[red]An error occurred:[/red] {str(e)}")
        return None


def copy_transcription_to_clipboard(text):
    """Copy the transcribed text to clipboard using pyperclip."""
    pyperclip.copy(text)
    pyautogui.hotkey("alt+z")


def main():
    title = "[cyan]Groq Whisperer[/cyan]\n" "[dim]Voice transcription powered by Groq[/dim]"
    console.print(Panel.fit(title, border_style="cyan"))

    layout = Layout()
    layout.split_column(Layout(name="header", size=3), Layout(name="body"), Layout(name="footer", size=3))

    layout["header"].update(Align.center("[bold cyan]Groq Whisperer[/bold cyan]"))
    layout["footer"].update(Align.center("[yellow]Press alt+x to start recording[/yellow]"))

    with Live(layout, refresh_per_second=4, screen=True):
        while True:
            # Record audio
            frames, sample_rate = record_audio()

            # Save audio to temporary file
            temp_audio_file = save_audio(frames, sample_rate)

            # Transcribe audio
            transcription = transcribe_audio(temp_audio_file)

            # Copy transcription to clipboard
            if transcription:
                layout["body"].update(Panel(transcription, border_style="green"))
                console.print("[yellow]Copying to clipboard...[/yellow]")
                copy_transcription_to_clipboard(transcription)
                msg = "[green]✓[/green] Transcription copied and pasted"
                console.print(msg)
            else:
                layout["body"].update(Panel("[red]Transcription failed.[/red]", border_style="red"))

            # Clean up temporary file
            os.unlink(temp_audio_file)

            layout["footer"].update(Align.center("[yellow]Ready for next recording. Press alt+x to start.[/yellow]"))


if __name__ == "__main__":
    main()
