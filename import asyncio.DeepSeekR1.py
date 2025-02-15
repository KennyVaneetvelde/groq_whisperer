import asyncio

"""
Module DeepSeekR1
This module implements a voice transcription system capable of recording audio, processing it using an external
transcription API, and displaying the results via both CLI and GUI interfaces. It also handles network connectivity,
VPN management, and audio feedback.
Classes:
    Config:
        A singleton class that manages application configuration including settings for logging, VPN usage, GUI activation,
        connection timeouts, and audio feedback.
    TranscriptionLogger:
        Configures and initializes the logging system for the application, setting up both file and console handlers
        using the logging level defined in the configuration.
    NetworkManager:
        Manages network-related tasks, including retrieving the public IP address and checking connectivity to a given URL,
        with configurable timeouts and retry mechanisms.
    VPNController:
        Handles VPN connections using OpenVPN. It provides asynchronous methods to establish a VPN connection based on a
        provided configuration, verifies connectivity, and includes functionality to disconnect the VPN by terminating the
        associated process.
    AudioFeedback:
        Manages the playback of audio cues using the pygame mixer. It loads specified sound files for start and completion events
        and plays them when triggered, provided audio feedback is enabled in the configuration.
    TranscriptionGUI:
        Implements a simple graphical user interface (GUI) using Tkinter for the transcription system. The GUI offers controls
        to initiate recording (mapped to a key combination), displays status updates, shows the transcript, and provides visual
        progress indication along with audio feedback.
    TranscriptionEngine:
        Serves as the core engine for audio recording and transcription. It captures audio using PyAudio, saves recordings
        to a temporary WAV file, interacts with a transcription API (via the Groq client), and handles the processing of the
        transcription result, including clipboard copying and audio feedback notifications.
    Application:
        Orchestrates the overall workflow of the transcription system. Depending on the configuration, it can run in either
        CLI mode or GUI mode. In CLI mode, it continuously listens for key events to record audio, transcribes the captured
        audio, and provides feedback until interrupted. In GUI mode, it launches the Tkinter-based user interface for
        interactive control.
Usage:
    To run the application, execute the module as the main program. The behavior is determined by the 'enable_gui' flag in the
    configuration:
      - When GUI is disabled, the application runs in CLI mode with continuous asynchronous transcription.
      - When GUI is enabled, the Tkinter interface is launched.
Notes:
    - The application depends on external modules such as PyAudio, pygame, keyboard, requests, and a Groq API client.
    - Audio files for feedback (e.g., "assets/start.wav" and "assets/complete.wav") must be available in the working directory.
    - VPN functionality requires a valid OpenVPN configuration file and the correct path to the OpenVPN executable.
    - Handle exceptions like FileNotFoundError and ModuleNotFoundError when required files or dependencies are missing.
"""
import json
import logging
import os
import subprocess
import tempfile
import wave
from configparser import ConfigParser
from datetime import datetime
from tkinter import Button, Frame, Label, StringVar, Tk, ttk
from urllib.parse import urlparse

import keyboard
import numpy as np
import pyaudio
import pyautogui
import pygame
import pyperclip
import requests
from groq import Groq
from pygame import mixer
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from rich.console import Console
from rich.panel import Panel


def create_beep(filename, frequency, duration=0.15, amplitude=0.5, sample_rate=44100):
    """Create a simple beep WAV file."""
    t = np.linspace(0, duration, int(sample_rate * duration))
    samples = amplitude * np.sin(2 * np.pi * frequency * t)
    samples = (samples * 32767).astype(np.int16)

    with wave.open(filename, "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())


def create_default_sounds():
    assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    os.makedirs(assets_dir, exist_ok=True)

    sounds = {"start.wav": 800, "complete.wav": 1000}

    for filename, frequency in sounds.items():
        filepath = os.path.join(assets_dir, filename)
        if not os.path.exists(filepath):
            create_beep(filepath, frequency)
            print(f"Created {filename}")


if __name__ == "__main__":
    create_default_sounds()


# Configuration Management
class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.load_config()
        return cls._instance

    def load_config(self):
        self.config = {
            "logging_level": "INFO",
            "use_vpn": False,
            "vpn_config_path": "D:\\git\\groq2\\ovpns\\199.180.137.197.ovpn",
            "openvpn_path": "C:\\Program Files\\OpenVPN\\bin\\openvpn.exe",
            "enable_gui": False,
            "connection_timeout": 5,
            "audio_feedback": True,
        }

    def __getattr__(self, name):
        return self.config.get(name)


# Logging System
class TranscriptionLogger:
    def __init__(self):
        self.logger = logging.getLogger("transcription")
        self.logger.setLevel(Config().logging_level)

        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

        # File handler
        file_handler = logging.FileHandler("transcription.log")
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)


logger = TranscriptionLogger().logger


# Network Connectivity
class NetworkManager:
    def __init__(self):
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def get_public_ip(self):
        try:
            return self.session.get("https://api.ipify.org", timeout=3).text
        except Exception:
            return "Unknown"

    def check_connection(self, url="https://api.groq.com"):
        try:
            response = self.session.get(url, timeout=Config().connection_timeout)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Connection check failed: {e}")
            return False


# VPN Management
class VPNController:
    def __init__(self):
        self.config = Config()

    async def connect(self):
        if not self.config.use_vpn:
            logger.info("VPN connection skipped per configuration")
            return True

        try:
            if not os.path.exists(self.config.vpn_config_path):
                logger.error("OpenVPN configuration file not found")
                return False

            logger.info("Establishing VPN connection...")
            subprocess.Popen([self.config.openvpn_path, "--config", self.config.vpn_config_path])
            await asyncio.sleep(5)
            return self.verify_connection()
        except Exception as e:
            logger.error(f"VPN connection failed: {e}")
            return False

    def verify_connection(self):
        nm = NetworkManager()
        pre_ip = nm.get_public_ip()
        if nm.check_connection():
            logger.info(f"VPN Connected - Public IP: {pre_ip}")
            return True
        return False

    def disconnect(self):
        subprocess.run(["taskkill", "/F", "/IM", "openvpn.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# Audio System
class AudioFeedback:
    def __init__(self):
        self.sounds = {}
        self.use_fallback = False

        # Ensure assets directory exists
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        os.makedirs(assets_dir, exist_ok=True)

        try:
            mixer.init()
            self._load_sounds(assets_dir)
        except Exception as e:
            logger.warning(f"Failed to initialize audio mixer: {e}")
            self.use_fallback = True

    def _load_sounds(self, assets_dir):
        """Load sound files or use fallback frequencies."""
        sound_files = {
            "start": ("start.wav", 800),  # 800 Hz fallback
            "complete": ("complete.wav", 1000),  # 1000 Hz fallback
        }

        for sound_name, (filename, fallback_freq) in sound_files.items():
            sound_path = os.path.join(assets_dir, filename)
            try:
                if os.path.exists(sound_path):
                    self.sounds[sound_name] = {"sound": mixer.Sound(sound_path), "fallback_freq": fallback_freq}
                else:
                    logger.warning(f"{filename} not found - using system beep fallback")
                    self.sounds[sound_name] = {"sound": None, "fallback_freq": fallback_freq}
            except Exception as e:
                logger.warning(f"Failed to load {filename}: {e}")
                self.sounds[sound_name] = {"sound": None, "fallback_freq": fallback_freq}

    def play(self, sound_type):
        """Play sound with fallback to system beep if file unavailable."""
        if not Config().audio_feedback:
            return

        if sound_type not in self.sounds:
            logger.warning(f"Unknown sound type: {sound_type}")
            return

        sound_data = self.sounds[sound_type]

        try:
            if not self.use_fallback and sound_data["sound"]:
                sound_data["sound"].play()
            else:
                # Fallback to system beep
                import winsound

                winsound.Beep(sound_data["fallback_freq"], 150)
        except Exception as e:
            logger.error(f"Failed to play sound {sound_type}: {e}")

    def cleanup(self):
        """Cleanup mixer resources."""
        try:
            mixer.quit()
        except Exception:
            pass


# GUI Interface
class TranscriptionGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice Transcription")
        self.audio_feedback = AudioFeedback()

        self.create_widgets()

    def create_widgets(self):
        self.main_frame = ttk.Frame(self.root, padding=20)
        self.main_frame.pack(fill="both", expand=True)

        self.status_var = StringVar(value="Ready")
        self.transcript_var = StringVar()

        ttk.Button(self.main_frame, text="Start Recording (Alt+X)", command=self.start_recording).pack(pady=10)

        ttk.Label(self.main_frame, textvariable=self.status_var, font=("Arial", 12)).pack(pady=5)

        ttk.Label(self.main_frame, text="Transcript:", font=("Arial", 10, "bold")).pack(pady=5)

        ttk.Label(self.main_frame, textvariable=self.transcript_var, wraplength=400).pack(pady=10)

        self.progress = ttk.Progressbar(self.main_frame, mode="indeterminate")

    def start_recording(self):
        self.status_var.set("Recording... (Release Alt+X to stop)")
        self.progress.pack(pady=5)
        self.progress.start()
        self.audio_feedback.play("start")

    def show_result(self, text):
        self.progress.stop()
        self.progress.pack_forget()
        self.status_var.set("Ready")
        self.transcript_var.set(text)
        self.audio_feedback.play("complete")


# Core Functionality
class TranscriptionEngine:
    def __init__(self):
        self.config = Config()
        self.groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.console = Console()
        self.audio = AudioFeedback()
        self.network = NetworkManager()

    async def record_audio(self, sample_rate=16000):
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=sample_rate, input=True, frames_per_buffer=1024)
        frames = []

        keyboard.wait("alt+x")
        self.audio.play("start")
        logger.info("Recording started")

        while keyboard.is_pressed("alt+x"):
            frames.append(stream.read(1024))

        stream.stop_stream()
        stream.close()
        p.terminate()
        return frames, sample_rate

    def save_temp_audio(self, frames, sample_rate):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(pyaudio.PyAudio().get_sample_size(pyaudio.paInt16))
                wf.setframerate(sample_rate)
                wf.writeframes(b"".join(frames))
            return f.name

    async def transcribe(self, audio_path):
        try:
            with open(audio_path, "rb") as f:
                result = self.groq_client.audio.transcriptions.create(
                    file=(os.path.basename(audio_path), f),
                    model="whisper-large-v3",
                    prompt="Technical programming content",
                    response_format="text",
                )
            return result
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None


# Application Controller
class Application:
    def __init__(self):
        self.config = Config()
        self.engine = TranscriptionEngine()
        self.vpn = VPNController()

    async def run_cli(self):
        self.engine.console.print(
            Panel.fit("[bold cyan]Voice Transcription System[/]\n[dim]Powered by Groq[/]", border_style="cyan")
        )

        logger.info(f"Initial network check - Public IP: {self.engine.network.get_public_ip()}")

        if not await self.vpn.connect():
            logger.warning("Proceeding without VPN connection")

        try:
            while True:
                frames, rate = await self.engine.record_audio()
                temp_file = self.engine.save_temp_audio(frames, rate)

                with self.engine.console.status("[bold green]Processing..."):
                    transcript = await self.engine.transcribe(temp_file)

                os.unlink(temp_file)

                if transcript:
                    self.engine.audio.play("complete")
                    pyperclip.copy(transcript)
                    self.engine.console.print(f"[bold green]Transcript:[/]\n{transcript}")
                    logger.info("Transcript copied to clipboard")

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self.vpn.disconnect()

    def run_gui(self):
        root = Tk()
        gui = TranscriptionGUI(root)

        async def gui_task():
            while True:
                root.update()
                await asyncio.sleep(0.1)

        asyncio.run(gui_task())


if __name__ == "__main__":
    app = Application()

    if Config().enable_gui:
        app.run_gui()
    else:
        asyncio.run(app.run_cli())
