## Qué cambia

<!-- Una frase. Si son varias cosas, la lista va abajo. -->

## Por qué

<!-- El problema que resuelve, no la solución. -->

## Tipo

- [ ] Corrección de error
- [ ] Mejora
- [ ] Seguridad
- [ ] Documentación
- [ ] Refactor sin cambio de comportamiento

## Lista de verificación

- [ ] `python -m pytest tests/ -q` pasa en local
- [ ] Añadí o actualicé tests si el cambio lo necesita
- [ ] No he introducido datos ficticios en la interfaz: si un estado está
      vacío, se muestra vacío
- [ ] No he metido claves, tokens ni rutas personales
- [ ] Si toca `src/zix/`, lo he hecho a propósito y lo explico abajo

## Avisas de las zonas delicadas

Estas partes no se tocan por capricho. Si tu cambio las afecta, explica el
porqué aquí; si no las tocas, marca esta casilla:

- [ ] No toco `src/zix/` en zonas de voz, herramientas o STT
- [ ] No toco la CSP de `apps/zix-ui/`
- [ ] No toco `open_app` sin añadir el motivo a `FORBIDDEN_BINARIES`
- [ ] No toco `.env`

## Seguridad

Si has encontrado una vulnerabilidad, **no abras un PR**. Sigue
[SECURITY.md](SECURITY.md).