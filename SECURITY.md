# Seguridad

## Como reportar

Abre un issue privado en https://github.com/ZXcris/zix-bot-project con el
detalle, o escribe directamente al mantenedor. **No abras un issue publico**
para reportar una vulnerabilidad: hazlo publico solo cuando haya una version
corregida.

## Alcance

| Si es... | Entonces |
|---|---|
| Un fallo en el pipeline de voz | Vulnerabilidad: puede procesar audio no previsto |
| Una clave o dato personal en el repo o su historial | **Urgente**: hay que reescribir el historial |
| XSS en `apps/zix-ui/` | Vulnerabilidad |
| Un modelo que no reconoce la palabra de activacion | No es vulnerabilidad, es funcionalidad pendiente |

## Estado de seguridad (2026-10-03)

Revisado antes de la primera publicacion:

- **0 CVEs conocidas** en las **18 dependencias directas** (API de OSV),
  incluido `sounddevice 0.5.6`, cuya primera consulta falló por un corte de red
  y se repitió hasta confirmar 0.
- **Versiones fijadas con hashes.** `requirements.lock` fija los 48 paquetes del
  entorno con sus sha256 de PyPI, validado con
  `pip install --require-hashes --dry-run`. Instalar sin ese fichero deja la
  puerta abierta a que una dependencia publique una versión alterada.
- **Sin secretos** en el historial: `.env` nunca se versiono, y no hay claves
  de Groq, OpenAI, Anthropic, GitHub, AWS ni Slack en ningun commit. Tras el
  saneamiento, los commits antiguos dejaron de ser descargables desde GitHub.
- **CSP** declarada en las cuatro pantallas, con `connect-src 'none'`: la
  interfaz no puede salir a la red.
- **Sin XSS**: la UI escapa `& < > " '` antes de interpolar en `innerHTML`.
- **Sin `eval`, `pickle`, `os.system`, `shell=True` ni `verify=False`.**
- ZX Ops escucha solo en `127.0.0.1` y no se distribuye.

## Controles de privacidad del STT (2026-10-09)

El audio es el dato mas sensible que maneja ZIX. Tres controles, en este orden
dedecision:

1. **Interruptor** — `STT_ALLOW_CLOUD=0` impide cualquier envio cuando el STT
   activo es de nube. El pipeline se niega a arrancar y dice que hacer.
2. **Proveedor local** — `STT_PROVIDER=local` transcribe con faster-whisper en
   el equipo: el audio no sale nunca. `auto` usa local si esta disponible.
3. **Filtro previo a la subida** — `upload_guard` decide ANTES de transcribir,
   con Silero en local y sin red: descarta silencio, ruido y audio mas largo
   que `STT_MAX_SECONDS`.

Por que el filtro va antes y no despues: `is_valid_order()` se ejecuta cuando
el audio **ya subio**. Es una comprobacion de calidad del texto, no una puerta.

Que NO resuelve esto: decidir si el audio contiene una orden dirigida a ZIX. Eso
exige transcribir, y transcribir es precisamente lo que sube el audio. El
cambio real llega cuando el wake word responda a la voz del usuario.

Comprobado con audio real: una grabacion de voz propia pasa (83% de voz); un
tono sintetico y el silencio se descartan sin enviar nada.

## Limitaciones conocidas

1. **El STT sale a la nube.** Con `groq` configurado, el audio se envia a
   `api.groq.com`. Sin internet, ZIX no transcribe. No hay STT local.
2. **El pipeline es bloqueante.** Mientras ZIX habla, el microfono se apaga.
   Sin full-duplex ni cancelacion de eco, el altavoz puede realimentarse en el
   microfono.
3. **El wake word propio no es fiable.** Acierta 4/27 (15%) sobre voz humana
   real; por eso `.env` usa `hey_jarvis`, que escucha "Hey Jarvis" y no
   "Hey ZIX". Ese encadenamiento es el riesgo de privacidad mas serio que
   queda: un podcast que diga "Hey Jarvis" despierta ZIX, que graba lo que
   suene despues y lo envia a Groq. Se cierra reentrenando `zix.onnx` con voz
   humana.

## Corregido el 2026-10-09

- **`open_app` permitia abrir una terminal.** `KNOWN_APPS` contenia
  `"terminal": ["wt.exe", "cmd.exe"]`, lo que anulaba el diseno de "herramientas
  seguras": una inyeccion de prompt bastaba para abrir un interprete de
  comandos. Se quito de la lista y se anadio `FORBIDDEN_BINARIES` (33
  interpretes, scripts y binarios de descarga) como segunda barrera en
  runtime, por si alguien reintroduce uno. `tests/test_open_app.py` (15 tests)
  vigila la invariante.
- **`innerHTML` sin escape en la consola ZX Ops.** Anadio `esc()` y aplicado a
  los campos de texto libre. Verificado inyectando HTML en un nombre de
  agente: 0 nodos ejecutados.

Nota de correccion: el tope de `Content-Length` en `zxops_server.py` se
reporto como ausente en un escaneo previo. **Es falso positivo**: el limite de
64 KB esta en la linea siguiente a la lectura, y `rfile.read` solo aparece una
vez en todo el fichero.
