import asyncio
import json
import os
import platform
import socket
import subprocess
import tempfile
import wave
import winsound

import keyboard
import psutil
import pyaudio
import pyautogui
import pyperclip
import requests
import urllib3
from groq import Groq
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Constants
SOUND_START = 800  # frequency in Hz
SOUND_STOP = 600
SOUND_COMPLETE = 1000
SOUND_DURATION = 150  # milliseconds

OVPN_PATH = "D:\\git\\groq2\\ovpns\\199.180.137.197.ovpn"
OPENVPN_EXE = "C:\\Program Files\\OpenVPN\\bin\\openvpn.exe"

# Set up Groq client
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise ValueError("Please set the GROQ_API_KEY environment variable")
client = Groq(api_key=api_key)

# Initialize rich console
console = Console()


# Function to play notification sound
def play_notification(frequency):
    winsound.Beep(frequency, SOUND_DURATION)


# OpenVPN Setup (modular with user choice)
async def setup_ovpn_connection(use_vpn=True):
    """Set up OpenVPN connection if user chooses."""
    if not use_vpn:
        console.print("[green]VPN not used.[/green]")
        return True
    try:
        if not os.path.exists(OVPN_PATH):
            console.print(f"[red]Error: OpenVPN configuration file not found at {OVPN_PATH}[/red]")
            return False
        subprocess.Popen([OPENVPN_EXE, "--config", OVPN_PATH])
        await asyncio.sleep(5)  # Wait for connection to establish
        return True if check_vpn() else False
    except Exception as e:
        console.print(f"[red]Error setting up VPN: {e}[/red]")
        return False


def check_vpn():
    """Check if VPN is connected."""
    try:
        response = requests.get("https://api.groq.com", timeout=2)
        print(f"[yellow]Connected via IP: {get_ip_address()}[/yellow]")
        return True
    except requests.RequestException:
        return False


def cleanup_ovpn():
    """Clean up OpenVPN connection."""
    subprocess.run(["taskkill", "/F", "/IM", "openvpn.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# Get system IP address (useful for checking network connection)
def get_ip_address():
    """Get the current external IP address"""
    ip = requests.get("https://api64.ipify.org").text
    return ip


# Audio Recording
def record_audio(sample_rate=16000, channels=1, chunk=1024):
    """Record audio while alt+x is held down."""
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=channels, rate=sample_rate, input=True, frames_per_buffer=chunk)
    frames = []

    keyboard.wait("alt+x")
    play_notification(SOUND_START)
    console.print("[green]Recording... (Release alt+x to stop)[/green]")

    while keyboard.is_pressed("alt+x"):
        frames.append(stream.read(chunk))

    play_notification(SOUND_STOP)
    console.print("[blue]Recording finished.[/blue]")

    stream.stop_stream()
    stream.close()
    p.terminate()

    return frames, sample_rate


# Save Audio
def save_audio(frames, sample_rate):
    """Save recorded audio to a temporary WAV file."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
        with wave.open(temp_audio.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(pyaudio.PyAudio().get_sample_size(pyaudio.paInt16))
            wf.setframerate(sample_rate)
            wf.writeframes(b"".join(frames))
        return temp_audio.name


# Transcription Function
def transcribe_audio(audio_file_path):
    """Transcribe audio using Groq API."""
    try:
        with open(audio_file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(audio_file_path), file.read()),
                model="whisper-large-v3",
                prompt="The audio is by a programmer discussing programming issues...",
                response_format="text",
                language="en",
            )
        return transcription
    except Exception as e:
        console.print(f"[red]Transcription failed: {e}[/red]")
        return None


# Optional GUI Interface
import tkinter as tk
from tkinter import ttk


class TranscriptionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Transcription")

        # Create main frame
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Add controls
        self.start_button = ttk.Button(self.main_frame, text="Start", command=self.start_transcription)
        self.start_button.grid(row=0, column=0, padx=5, pady=5)

        self.status_label = ttk.Label(self.main_frame, text="Ready")
        self.status_label.grid(row=1, column=0, padx=5, pady=5)

    def start_transcription(self):
        # Implementation of transcription start
        pass


# Main Function
async def main():
    """Main application loop."""
    title = "[cyan]Groq Whisperer[/cyan]\n[dim]Voice transcription powered by Groq[/dim]"
    console.print(Panel.fit(title, border_style="cyan"))

    use_vpn = console.input("[yellow]Would you like to use OpenVPN? (yes/no): ").strip().lower() == "yes"

    if not await setup_ovpn_connection(use_vpn):
        console.print("[yellow]⚠ Failed to establish OpenVPN connection![/yellow]")

    try:
        while True:
            frames, sample_rate = record_audio()
            temp_audio_file = save_audio(frames, sample_rate)
            transcription = transcribe_audio(temp_audio_file)

            if transcription:
                play_notification(SOUND_COMPLETE)
                console.print(f"[bold green]Transcription:\n{transcription}[/bold green]")
                pyperclip.copy(transcription)
                console.print("[green]✓ Transcription copied to clipboard[/green]")
            else:
                console.print("[red]✗ Transcription failed.[/red]")

            os.unlink(temp_audio_file)

    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    finally:
        cleanup_ovpn()


if __name__ == "__main__":
    asyncio.run(main())
