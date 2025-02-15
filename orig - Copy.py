import os
import socket
import tempfile
import wave
import winsound
from msvcrt import getch

import keyboard
import pyaudio
import pyautogui
import pyperclip
import requests
from groq import Groq
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Initialize rich console
console = Console()

# Constants
SOUND_START = 800
SOUND_STOP = 600
SOUND_COMPLETE = 1000
SOUND_DURATION = 150


def init_groq():
    """Initialize Groq client."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        msg = "[red]Error:[/red] Please set the GROQ_API_KEY environment variable"
        console.print(Panel.fit(msg))
        raise ValueError("GROQ_API_KEY not set")
    return Groq(api_key=api_key)


client = init_groq()


def play_notification(frequency):
    """Play a brief notification sound."""
    try:
        winsound.Beep(frequency, SOUND_DURATION)
    except Exception:
        pass


def record_audio(sample_rate=16000, channels=1, chunk=1024):
    """Record audio from the microphone."""
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=channels,
        rate=sample_rate,
        input=True,
        frames_per_buffer=chunk,
    )

    console.print(Panel.fit("[yellow]Press and hold alt+x to start recording...[/yellow]"))
    frames = []

    # Wait for key press
    keyboard.wait("alt+x")
    play_notification(SOUND_START)
    console.print("[green]Recording...[/green] (Release alt+x to stop)")

    # Record while key is held
    while keyboard.is_pressed("alt+x"):
        data = stream.read(chunk)
        frames.append(data)

    play_notification(SOUND_STOP)
    console.print("[blue]Recording finished.[/blue]")

    # Cleanup
    stream.stop_stream()
    stream.close()
    p.terminate()

    return frames, sample_rate


def save_audio(frames, sample_rate):
    """Save recorded audio to temp file."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        with wave.open(temp_audio.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(pyaudio.PyAudio().get_sample_size(pyaudio.paInt16))
            wf.setframerate(sample_rate)
            wf.writeframes(b"".join(frames))
        return temp_audio.name


def transcribe_audio(audio_file_path):
    """Transcribe audio using Groq API."""
    try:
        with open(audio_file_path, "rb") as file:
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
                progress.add_task("Transcribing audio...", total=None)

                # Convert audio to base64
                import base64

                audio_data = base64.b64encode(file.read()).decode("utf-8")

                response = client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a speech-to-text transcription assistant. Convert the audio to text accurately.",
                        },
                        {"role": "user", "content": f"Here is the audio file encoded in base64: {audio_data}"},
                    ],
                    model="claude-3-opus-20240229",
                    temperature=0.1,
                    max_tokens=4096,
                    top_p=0.9,
                )
                return response.choices[0].message.content

    except Exception as e:
        console.print(f"[red]Transcription error:[/red] {str(e)}")
        return None


def main():
    """Main application function."""
    console.print(
        Panel.fit("[cyan]Groq Whisperer[/cyan]\n[dim]Voice transcription powered by Groq[/dim]", border_style="cyan")
    )

    try:
        while True:
            # Record audio
            frames, sample_rate = record_audio()

            # Save to temp file
            temp_audio_file = save_audio(frames, sample_rate)

            try:
                # Transcribe
                transcription = transcribe_audio(temp_audio_file)

                if transcription:
                    play_notification(SOUND_COMPLETE)
                    console.print("\n[green]Transcription:[/green]")
                    console.print(Panel(transcription, border_style="green"))

                    # Copy to clipboard
                    pyperclip.copy(transcription)
                    pyautogui.hotkey("alt+z")
                    console.print("[green]✓[/green] Transcription copied to clipboard")
                else:
                    console.print("[red]✗ Transcription failed[/red]")

            finally:
                # Cleanup temp file
                if os.path.exists(temp_audio_file):
                    os.unlink(temp_audio_file)

            # Ready for next recording
            console.print("\n[yellow]Ready for next recording. Press alt+x to start.[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Application terminated by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]An unexpected error occurred: {str(e)}[/red]")


if __name__ == "__main__":
    main()
