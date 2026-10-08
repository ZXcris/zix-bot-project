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

- **0 CVEs conocidas** en las 18 dependencias directas (API de OSV).
  `sounddevice 0.5.6` no pudo consultarse ese dia; repetir.
- **Sin secretos** en el historial: `.env` nunca se versiono, y no hay claves
  de Groq, OpenAI, Anthropic, GitHub, AWS ni Slack en ningun commit.
- **CSP** declarada en las cuatro pantallas, con `connect-src 'none'`: la
  interfaz no puede salir a la red.
- **Sin XSS**: la UI escapa `& < > " '` antes de interpolar en `innerHTML`.
- **Sin `eval`, `pickle`, `os.system`, `shell=True` ni `verify=False`.**
- ZX Ops escucha solo en `127.0.0.1` y no se distribuye.

## Limitaciones conocidas

1. **El STT sale a la nube.** Con `groq` configurado, el audio se envia a
   `api.groq.com`. Sin internet, ZIX no transcribe. No hay STT local.
2. **El pipeline es bloqueante.** Mientras ZIX habla, el microfono se apaga.
   Sin full-duplex ni cancelacion de eco, el altavoz puede realimentarse en el
   microfono.
3. **`zxops_server.py` no limita `Content-Length`.** Escucha solo en localhost,
   pero un `Content-Length` enorme puede agotar memoria. Pendiente de un tope.
4. **El wake word propio no es fiable.** Acierta 4/27 (15%) sobre voz humana
   real; por eso `.env` usa `hey_jarvis`. Ver `docs/SESSION_STATE.md`.
