@echo off
powershell Start-Process python -ArgumentList "orig.py" -Verb RunAs -Wait
