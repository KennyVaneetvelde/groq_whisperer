import os
import tempfile
import wave

import keyboard
import pyaudio
import pyautogui
import pyperclip
from groq import Groq
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import requests
import socket
import urllib3

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


def check_vpn():
    """Check if VPN is likely active by trying to detect proxy settings."""
    try:
        # Try to detect proxy settings
        response = requests.get('https://api.groq.com', timeout=5)
        if response.raw.connection.sock.getpeername()[0] != socket.gethostbyname(urllib3.util.url.parse_url('https://api.groq.com').host):
            return True
        return False
    except Exception:
        # If any error occurs during check, assume no VPN
        return False


def main():
    """Main application function."""
    title = "[cyan]Groq Whisperer[/cyan]\n[dim]Voice transcription powered by Groq[/dim]"
    console.print(Panel.fit(title, border_style="cyan"))

    # Add VPN check
    if check_vpn():
        warning = (
            "[yellow]⚠ VPN detected![/yellow]\n"
            "The Groq API may not work correctly with VPN connections.\n"
            "If you experience 404 errors, try disabling your VPN."
        )
        console.print(Panel.fit(warning, border_style="yellow"))
        proceed = input("Do you want to continue anyway? (y/n): ").lower()
        if proceed != 'y':
            return

    while True:
        # Record audio
        frames, sample_rate = record_audio()

        # Save audio to temporary file
        temp_audio_file = save_audio(frames, sample_rate)

        # Transcribe audio
        transcription = transcribe_audio(temp_audio_file)

        # Copy transcription to clipboard
        if transcription:
            console.print("\n[bold green]Transcription:[/bold green]")
            console.print(Panel(transcription, border_style="green"))
            console.print("[yellow]Copying to clipboard...[/yellow]")
            copy_transcription_to_clipboard(transcription)
            msg = "[green]✓[/green] Transcription copied and pasted"
            console.print(msg)
        else:
            console.print("[red]✗ Transcription failed.[/red]")

        # Clean up temporary file
        os.unlink(temp_audio_file)

        msg = "\n[yellow]Ready for next recording. Press alt+x to start.[/yellow]"
        console.print(msg)


if __name__ == "__main__":
    main()
