import asyncio
import json
import logging
import os
import socket
import subprocess
import tempfile
import wave
from configparser import ConfigParser
from datetime import datetime
from tkinter import Button, Frame, Label, StringVar, Tk, ttk
from urllib.parse import urlparse

import keyboard
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
        mixer.init()
        self.sounds = {"start": mixer.Sound("assets/start.wav"), "complete": mixer.Sound("assets/complete.wav")}

    def play(self, sound_type):
        if Config().audio_feedback and sound_type in self.sounds:
            self.sounds[sound_type].play()


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
