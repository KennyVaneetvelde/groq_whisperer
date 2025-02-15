import asyncio
import json
import os
import subprocess
import tempfile
import wave
import winsound

import keyboard
import pyaudio
import pyperclip
import requests
from groq import Groq
from rich.console import Console
from rich.panel import Panel

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
        
        # Start OpenVPN with timeout
        process = subprocess.Popen([OPENVPN_EXE, "--config", OVPN_PATH])
        
        # Wait for connection with timeout
        for _ in range(30):  # 30 second timeout
            await asyncio.sleep(1)
            if check_vpn():
                return True
        
        console.print("[red]VPN connection timed out[/red]")