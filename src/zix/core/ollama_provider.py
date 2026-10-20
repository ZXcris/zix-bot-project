"""Implementación de AIProvider usando Ollama (modelo local).

Por qué existe:

    Los dos proveedores de nube están caídos en este equipo. Groq devuelve
    HTTP 403 (error 1010 de Cloudflare: bloquea esta conexión, no es la
    clave) y xKiro no tiene clave puesta en .env. Con lo cual ZIX no
    contestaba nada.

    Ollama ya está corriendo en este PC y expone un endpoint compatible
    con OpenAI (`POST {base_url}/chat/completions`). Por eso este proveedor
    habla el mismo formato que xKiro y solo usa `urllib` de la stdlib:
    no añade ninguna dependencia.

Ventajas frente a la nube:

    - Sin cuota, sin tokens, sin límites diarios.
    - No sale nada del equipo: ni las preguntas ni el audio.
    - Sigue funcionando sin internet.

Lo que tiene de malo, y hay que decirlo:

    - Va por CPU (este equipo no tiene GPU utilizable), asi que va lento:
      ~7 palabras por segundo, y el primer turno tarda mas porque el
      modelo pesa 1,5 GB y hay que cargarlo en RAM.
    - Solo uno de los tres modelos instalados emite tool calls de verdad
      (`openbmb/minicpm-v4.6`). El agente de ZIX vive de las tools, asi
      que ese es el modelo por defecto. Con `phi4-mini` o
      `qwen2.5-coder:1.5b` ZIX contesta pero no puede actuar.

Errores de red, timeouts y respuestas invalidas se traducen a los tipos
neutros (ProviderTimeoutError, etc.) y NUNCA se ocultan.
"""
from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from ..config import Config
from .ai_provider import (
    AIProvider,
    AIProviderError,
    AgentResponse,
    ChatMessage,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ToolCall,
    ToolSpec,
)

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"

# Esquemas que se permiten. urllib acepta otros (file:// lee ficheros
# locales con un POST, data:// y ftp:// tambien), y ZIX no los necesita:
# el motor local habla HTTP.
ESQUEMAS_PERMITIDOS = frozenset({"http", "https"})

# Nombres de modelo admitidos. Formato de Ollama: namespace/modelo:tag.
# Se rechaza cualquier cosa que parezca una traversía de ruta, porque el
# nombre se traduce a una ruta dentro del directorio de modelos de Ollama.
_RE_MODELO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


def _es_loopback(host: str) -> bool:
    """¿El host es esta misma máquina?"""
    if not host:
        return False
    host = host.strip("[]").lower()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    return host.startswith("127.")


def _registrar_respuesta_invalida(raw: str) -> None:
    """La respuesta cruda va al LOG, nunca al mensaje de cara al usuario.

    Ese mensaje lo lee el TTS en voz alta: si un endpoint hostil devuelve
    texto arbitrario, ZIX lo leeria en voz alta.
    """
    import logging

    logging.getLogger(__name__).warning(
        "Respuesta invalida de Ollama: %r", raw[:400]
    )


class OllamaProvider(AIProvider):
    """Proveedor de IA local vía Ollama.

    A diferencia de Groq y xKiro, NO hace falta ninguna clave: el modelo
    corre en este equipo.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._base_url = (config.ollama_base_url or DEFAULT_BASE_URL).rstrip("/")
        self._model = config.ollama_model
        self._validar_destino()
        self._validar_modelo()

    def _validar_destino(self) -> None:
        """No se puede enviar la conversacion a cualquier sitio.

        Sin esto, OLLAMA_BASE_URL es un SSRF: apunta a donde quiera y ZIX
        manda ahi el historial entero, que incluye la transcripcion de la
        voz del usuario. Y urllib acepta esquemas como file://, que leen
        ficheros locales.
        """
        partes = urllib.parse.urlsplit(self._base_url)
        if partes.scheme.lower() not in ESQUEMAS_PERMITIDOS:
            raise ValueError(
                f"OLLAMA_BASE_URL solo admite http o https, no "
                f"{partes.scheme!r}. ZIX habla con el motor local por HTTP."
            )
        if not _es_loopback(partes.hostname or ""):
            if not self._config.ollama_allow_remote:
                raise ValueError(
                    f"OLLAMA_BASE_URL apunta fuera de este equipo "
                    f"({partes.hostname}). Eso envia tu conversacion y la "
                    f"transcripcion de tu voz a un servidor remoto, en claro. "
                    f"Si es lo que quieres, pon OLLAMA_ALLOW_REMOTE=1."
                )

    def _validar_modelo(self) -> None:
        if not _RE_MODELO.match(self._model) or ".." in self._model:
            raise ValueError(
                f"OLLAMA_MODEL={self._model!r} no es un nombre de modelo "
                f"valido (namespace/modelo:tag)."
            )

    @property
    def model(self) -> str:
        return self._model

    def complete(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AgentResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_api_message(m) for m in messages],
            "stream": False,
        }
        api_tools = [self._to_api_tool(t) for t in tools]
        if api_tools:
            payload["tools"] = api_tools
        return self._request(payload)

    def _request(self, payload: dict[str, Any]) -> AgentResponse:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        # El PLAZO TOTAL. El timeout de urlopen es por operacion de socket,
        # no un deadline: medido en este equipo, contra un servidor que
        # mandaba un byte cada 0,2 s, urlopen(timeout=2) NO corto a los 2 s
        # sino a los 20 s. Con el pipeline de voz sincrono, eso deja a ZIX
        # sin microfono durante todo ese rato.
        plazo = time.monotonic() + self._config.ollama_timeout_seconds
        try:
            with urllib.request.urlopen(
                request, timeout=self._config.ollama_timeout_seconds
            ) as response:
                raw = self._leer_con_plazo(response, plazo)
        except urllib.error.HTTPError as exc:
            cuerpo = exc.read().decode("utf-8", "replace")[:200]
            if exc.code == 429:
                raise ProviderRateLimitError(
                    f"Ollama devuelve 429: {cuerpo}"
                ) from exc
            if exc.code == 404:
                raise AIProviderError(
                    f"Ollama no encuentra el modelo {self._model!r}. "
                    f"Comprueba 'ollama list' y ajusta OLLAMA_MODEL."
                ) from exc
            raise AIProviderError(f"Ollama HTTP {exc.code}: {cuerpo}") from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise ProviderTimeoutError(
                f"No se pudo hablar con Ollama en {self._base_url}: {exc}. "
                f"Comprueba que 'ollama serve' este corriendo."
            ) from exc

        try:
            body = json.loads(raw)
            choice = body["choices"][0]["message"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            # OJO: el contenido crudo NO se incluye en el mensaje. Ese
            # mensaje lo lee el TTS en voz alta, asi que lo que diga un
            # endpoint hostil seria audible. El detalle va al log.
            _registrar_respuesta_invalida(raw)
            raise ProviderInvalidResponseError(
                "La respuesta de Ollama no es un chat completion válido "
                "(la respuesta cruda está en el log)."
            ) from exc

        tool_calls: Optional[list[ToolCall]] = None
        raw_calls = choice.get("tool_calls") or []
        if len(raw_calls) > self._config.ollama_max_tool_calls:
            # El agente ejecuta TODAS las tool calls de un turno. Sin tope,
            # una respuesta con 100.000 llamadas abre 100.000 procesos.
            raise ProviderInvalidResponseError(
                f"Ollama devolvió {len(raw_calls)} tool calls y el tope es "
                f"{self._config.ollama_max_tool_calls}."
            )
        if raw_calls:
            tool_calls = []
            for raw_call in raw_calls:
                function = raw_call.get("function", {})
                arguments = function.get("arguments")
                # Ollama devuelve los argumentos como objeto JSON ya
                # parseado, a diferencia de OpenAI, que los manda como
                # cadena. Se aceptan las dos formas.
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments or "{}")
                    except json.JSONDecodeError as exc:
                        raise ProviderInvalidResponseError(
                            f"Argumentos de tool call inválidos: {arguments!r}"
                        ) from exc
                if not isinstance(arguments, dict):
                    raise ProviderInvalidResponseError(
                        f"Argumentos de tool call no son objeto: {arguments!r}"
                    )
                tool_calls.append(
                    ToolCall(
                        id=str(raw_call.get("id", "")),
                        name=str(function.get("name", "")),
                        arguments=arguments,
                    )
                )

        content = choice.get("content")
        if content is not None and not isinstance(content, str):
            raise ProviderInvalidResponseError(
                f"Contenido de respuesta no es texto: {content!r}"
            )
        return AgentResponse(content=content, tool_calls=tool_calls or None)

    # ------------------------------------------------------------------
    # Lectura con plazo total y tope de tamaño
    # ------------------------------------------------------------------
    def _leer_con_plazo(self, response: Any, plazo: float) -> str:
        """Lee la respuesta respetando el plazo total y un tope de bytes.

        Se lee en trozos con read1(), que devuelve lo que haya disponible
        sin esperar a llenar el buffer. Asi se puede comprobar el reloj
        entre trozos: con un read() normal, un servidor lento puede
        retener la llamada indefinidamente.
        """
        tope = self._config.ollama_max_response_bytes
        trozos: list[bytes] = []
        total = 0
        while True:
            restante = plazo - time.monotonic()
            if restante <= 0:
                raise ProviderTimeoutError(
                    f"Ollama tardó más de {self._config.ollama_timeout_seconds:.0f} s "
                    f"en responder. El plazo es total, no por operación."
                )
            # El timeout del socket se recorta al tiempo que queda, para
            # que una lectura bloqueada no pase del plazo.
            try:
                if hasattr(response, "read1"):
                    trozo = response.read1(65536)
                else:
                    trozo = response.read(65536)
            except (socket.timeout, TimeoutError) as exc:
                raise ProviderTimeoutError(
                    f"Ollama tardó más de {self._config.ollama_timeout_seconds:.0f} s "
                    f"en responder: {exc}"
                ) from exc
            if not trozo:
                break
            total += len(trozo)
            if total > tope:
                raise ProviderInvalidResponseError(
                    f"La respuesta de Ollama es demasiado grande (más de "
                    f"{tope} bytes). Se corta para no comerse la memoria."
                )
            trozos.append(trozo)
        return b"".join(trozos).decode("utf-8", "replace")

    # ------------------------------------------------------------------
    # Conversión de tipos neutros -> formato OpenAI (el que habla Ollama)
    # ------------------------------------------------------------------
    @staticmethod
    def _to_api_message(message: ChatMessage) -> dict[str, Any]:
        api: dict[str, Any] = {"role": message.role}
        if message.content is not None:
            api["content"] = message.content
        if message.tool_calls is not None:
            api["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id is not None:
            api["tool_call_id"] = message.tool_call_id
        return api

    @staticmethod
    def _to_api_tool(tool: ToolSpec) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
