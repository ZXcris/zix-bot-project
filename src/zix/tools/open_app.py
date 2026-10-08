"""Herramienta open_app: abre aplicaciones de escritorio de una LISTA BLANCA.

Seguridad: la herramienta solo acepta nombres de una lista blanca fija.
Nunca ejecuta comandos, scripts ni rutas arbitrarias proporcionadas por el
modelo; si la aplicación no está en la lista, rechaza la solicitud y
devuelve el motivo. No usa shell (subprocess.Popen sin shell=True).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

from ..core.tool import Tool

# Lista blanca: nombre canónico -> candidatos de resolución
# (nombres de ejecutable buscables en PATH y rutas conocidas de instalación).
KNOWN_APPS: dict[str, list[str]] = {
    "chrome": [
        "chrome.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        "msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "firefox": [
        "firefox.exe",
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
    ],
    "notepad": ["notepad.exe"],
    "paint": ["mspaint.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "terminal": ["wt.exe", "cmd.exe"],
    "word": [
        "winword.exe",
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    ],
    "excel": [
        "excel.exe",
        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    ],
    "powerpoint": [
        "powerpnt.exe",
        r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    ],
    "spotify": ["spotify.exe", r"%LOCALAPPDATA%\Spotify\Spotify.exe"],
    "vscode": ["code.exe", r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"],
    "discord": ["discord.exe", r"%LOCALAPPDATA%\Discord\Discord.exe"],
    "whatsapp": ["whatsapp.exe", r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe"],
}


def _resolve_candidates(candidates: list[str]) -> Optional[str]:
    for candidate in candidates:
        expanded = os.path.expandvars(candidate)
        if os.sep in expanded or "/" in expanded:
            if os.path.isfile(expanded):
                return expanded
        else:
            found = shutil.which(expanded)
            if found:
                return found
    return None


def open_app(app: str) -> str:
    """Abre una aplicación de la lista blanca. Rechaza cualquier otra."""
    key = app.strip().lower()
    if key not in KNOWN_APPS:
        return (
            f"Rechazada: '{app}' no está en la lista blanca de aplicaciones "
            f"permitidas ({', '.join(sorted(KNOWN_APPS))})."
        )
    resolved = _resolve_candidates(KNOWN_APPS[key])
    if resolved is None:
        return f"No se encontró el ejecutable de '{app}' en este equipo."
    subprocess.Popen([resolved])
    return f"Abierta: {app}."


open_app_tool = Tool(
    name="open_app",
    description=(
        "Abre una aplicación de escritorio instalada. Solo se permiten estas "
        "aplicaciones: " + ", ".join(sorted(KNOWN_APPS)) + "."
    ),
    parameters={
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": (
                    "Nombre de la aplicación a abrir, p. ej. 'chrome', "
                    "'notepad', 'spotify'."
                ),
            },
        },
        "required": ["app"],
    },
    func=open_app,
    metadata={"category": "system"},
)