import asyncio
import logging
import os
import re
import socket
import subprocess
import tempfile
import time
import wave
import winsound

import keyboard
import pyaudio
import pyautogui
import pyperclip
import requests
import urllib3
from groq import Groq
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Constants for logging configuration
ENABLE_LOGGING = True  # Toggle for enabling/disabling logging
LOG_LEVEL = "DEBUG"  # Can be "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"

# --- Logging Setup ---
if ENABLE_LOGGING:
    log_level = getattr(logging, LOG_LEVEL.upper())
    logging.basicConfig(
        filename="transcription_script.log",
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logging.info("Script started")

# Constants
SOUND_START_FILE = "start_click_quiet.wav"  # Replace with your quiet start sound file
SOUND_COMPLETE_FILE = "complete_chime_quiet.wav"  # Replace with your quiet complete sound file
SOUND_DURATION = 150
OVPN_PATH = "D:\\git\\groq2\\ovpns\\199.180.137.197.ovpn"
OPENVPN_EXE = "C:\\Program Files\\OpenVPN\\bin\\openvpn.exe"
AUTO_PASTE = True
CHECK_VPN_FEEDBACK = True  # Toggle for VPN feedback (IP, Latency)
USE_VPN = True  # Toggle for using VPN connection
VERBOSE_OUTPUT = True  # Toggle for verbose console output (True to show detailed output, False for minimal)

# Set up Groq client
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    error_message = "GROQ_API_KEY environment variable not set!"
    logging.error(error_message)
    raise ValueError(error_message)
client = Groq(api_key=api_key)
logging.info("Groq client initialized")

# Initialize rich console
console = Console()


# Function to play notification sound (using sound files - adjust as needed)
def play_notification(sound_type):
    if sound_type == "start":
        sound_file = SOUND_START_FILE
    elif sound_type == "complete":
        sound_file = SOUND_COMPLETE_FILE
    else:
        return

    if sound_file and os.path.exists(sound_file):
        winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NOSTOP)
    else:
        print(f"Warning: Sound file for '{sound_type}' not found or configured. Using default beep.")
        if sound_type == "start":
            winsound.Beep(2000, 50)
        elif sound_type == "complete":
            winsound.Beep(1500, 100)


def get_public_ip():
    """Fetches the current public IP address."""
    try:
        response = requests.get("https://ifconfig.me", timeout=5)  # Added timeout
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return response.text.strip()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching public IP: {e}")
        return None


def measure_latency(host="8.8.8.8"):
    """Measures latency to a host using ping and returns average latency in ms."""
    try:
        # -n 3 for 3 pings (Windows), -c 3 for Linux/macOS
        # -w 5000 timeout of 5000ms (5 seconds) for each ping (Windows)
        ping_cmd = ["ping", "-n", "3", "-w", "5000", host]
        process = subprocess.run(ping_cmd, capture_output=True, text=True, check=True)
        output = process.stdout

        # Regular expression to find average latency in Windows ping output
        latency_match = re.search(r"Average = (\d+)ms", output)
        if latency_match:
            return int(latency_match.group(1))  # Return average latency in milliseconds
        else:
            logging.warning("Could not parse latency from ping output.")
            return None
    except subprocess.CalledProcessError as e:
        logging.error(f"Ping command failed: {e}")
        return None
    except FileNotFoundError:
        logging.error("Ping command not found. Ensure 'ping' is in your system's PATH.")
        return None


def record_audio(sample_rate=16000, channels=1, chunk=1024):
    """Record audio while alt+x is held down."""
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=channels, rate=sample_rate, input=True, frames_per_buffer=chunk)
    frames = []

    keyboard.wait("alt+x")
    play_notification("start")
    console.print("[green]Recording... (Release alt+x to stop)[/green]")

    while keyboard.is_pressed("alt+x"):
        frames.append(stream.read(chunk))

    # play_notification("stop") # Removed stop sound
    console.print("[blue]Recording finished.[/blue]")
    stream.stop_stream()
    stream.close()
    p.terminate()

    return frames, sample_rate


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


def save_audio(frames, sample_rate):
    """Saves audio frames to a temporary WAV file."""
    temp_audio_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(temp_audio_file, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(pyaudio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))
    return temp_audio_file.name


async def setup_ovpn_connection():
    """Set up OpenVPN connection if USE_VPN is True, otherwise simulate."""
    if not USE_VPN:
        if VERBOSE_OUTPUT:
            console.print("[magenta]VPN usage is toggled OFF. Bypassing VPN connection setup.[/magenta]")
        return True  # Simulate successful VPN setup when VPN is toggled off

    if VERBOSE_OUTPUT:
        console.print("[magenta]Setting up OpenVPN connection...[/magenta]")

    if CHECK_VPN_FEEDBACK:
        if VERBOSE_OUTPUT:
            console.print("[cyan]Checking public IP before VPN connection...[/cyan]")
        initial_ip = get_public_ip()
        if initial_ip:
            if VERBOSE_OUTPUT:
                console.print(f"[cyan]Initial Public IP: [bold]{initial_ip}[/bold][/cyan]")
        else:
            if VERBOSE_OUTPUT:
                console.print("[yellow]⚠️ Could not retrieve initial public IP.[/yellow]")

    try:
        if not os.path.exists(OVPN_PATH):
            console.print(f"[red]Error: OpenVPN configuration file not found at {OVPN_PATH}[/red]")
            return False
        subprocess.Popen([OPENVPN_EXE, "--config", OVPN_PATH])
        await asyncio.sleep(5)  # Wait for connection to establish
        vpn_connected = check_vpn()
        if vpn_connected:
            if VERBOSE_OUTPUT:
                console.print("[green]✓ OpenVPN connection established.[/green]")
        else:
            console.print("[red]✗ Failed to establish OpenVPN connection (check_vpn failed).[/red]")
            return False

        if CHECK_VPN_FEEDBACK and vpn_connected:
            if VERBOSE_OUTPUT:
                console.print("[cyan]Checking public IP after VPN connection...[/cyan]")
            vpn_ip = get_public_ip()
            if vpn_ip:
                if VERBOSE_OUTPUT:
                    console.print(f"[cyan]Public IP after VPN: [bold]{vpn_ip}[/bold][/cyan]")
                if vpn_ip != initial_ip and initial_ip is not None:
                    if VERBOSE_OUTPUT:
                        console.print(f"[green]✓ Public IP changed, VPN likely active.[/green]")
                elif initial_ip is not None:
                    if VERBOSE_OUTPUT:
                        console.print(
                            "[yellow]⚠️ Public IP did not change after VPN. VPN might not be working as expected.[/yellow]"
                        )
                else:
                    if VERBOSE_OUTPUT:
                        console.print(
                            "[yellow]⚠️ Could not compare IP addresses as initial IP was not retrieved.[/yellow]"
                        )
            else:
                if VERBOSE_OUTPUT:
                    console.print("[yellow]⚠️ Could not retrieve public IP after VPN.[/yellow]")

            if VERBOSE_OUTPUT:
                console.print("[cyan]Measuring latency...[/cyan]")
            latency_ms = measure_latency()
            if latency_ms is not None:
                if VERBOSE_OUTPUT:
                    console.print(f"[cyan]Latency (ping to 8.8.8.8): [bold]{latency_ms} ms[/bold][/cyan]")
                    console.print(
                        "[cyan](This is the added latency due to network route, not just VPN overhead)[/cyan]"
                    )
                else:
                    if VERBOSE_OUTPUT:
                        console.print("[yellow]⚠️ Could not measure latency.[/yellow]")
            return vpn_connected

    except Exception as e:
        console.print(f"[red]Error setting up VPN: {e}[/red]")
        return False


def check_vpn():
    """Check if VPN is connected."""
    try:
        requests.get("https://api.groq.com", timeout=2)
        return True
    except requests.RequestException:
        return False


def cleanup_ovpn():
    """Clean up OpenVPN connection if USE_VPN is True."""
    if USE_VPN:
        if VERBOSE_OUTPUT:
            console.print("[magenta]Cleaning up OpenVPN connection...[/magenta]")
        subprocess.run(["taskkill", "/F", "/IM", "openvpn.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if VERBOSE_OUTPUT:
            console.print("[green]✓ OpenVPN processes terminated.[/green]")
    else:
        if VERBOSE_OUTPUT:
            console.print("[magenta]VPN usage is toggled OFF. Skipping OpenVPN cleanup.[/magenta]")


async def main():
    console.print(
        Panel.fit("[bold blue]Groq Whisperer[/bold blue]\nVoice transcription powered by Groq", border_style="blue")
    )
    if USE_VPN:
        if not await setup_ovpn_connection():
            if VERBOSE_OUTPUT:
                console.print(
                    "[yellow]⚠️ Failed to establish OpenVPN connection (and VPN is toggled ON). Script may not function correctly.[/yellow]"
                )
            logging.warning("OpenVPN connection failed, but VPN is toggled ON.")
    else:
        if VERBOSE_OUTPUT:
            console.print("[magenta]VPN usage is toggled OFF. Proceeding without VPN.[/magenta]")

    try:
        while True:
            frames, sample_rate = record_audio()
            temp_audio_file = save_audio(frames, sample_rate)
            transcription = transcribe_audio(temp_audio_file)

            if transcription:
                play_notification("complete")
                console.print(f"[bold green]Transcription:\n{transcription}[/bold green]")
                pyperclip.copy(transcription)
                console.print("[green]✓ Transcription copied to clipboard[/green]")
                if AUTO_PASTE:
                    time.sleep(0.1)
                    pyautogui.hotkey("ctrl", "v")
                    console.print("[green]✓ Transcription automatically pasted[/green]")
                    logging.info("Transcription successful and automatically pasted")
                else:
                    console.print("[blue](Automatic pasting disabled - transcription in clipboard only)[/blue]")
                    logging.info("Transcription successful - copied to clipboard only (auto-paste disabled)")
            else:
                console.print("[red]✗ Transcription failed.[/red]")
                logging.error("Transcription failed")

            os.unlink(temp_audio_file)
    except KeyboardInterrupt:
        if VERBOSE_OUTPUT:
            console.print("\n[yellow]Shutting down...[/yellow]")
        logging.info("Script shut down by user")
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
        logging.exception("Unexpected error during script execution")
    finally:
        if USE_VPN:
            cleanup_ovpn()
        logging.info("Script finished")


if __name__ == "__main__":
    asyncio.run(main())
