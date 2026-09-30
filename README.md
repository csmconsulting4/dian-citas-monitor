# DIAN Citas Monitor

Monitor gratuito de disponibilidad para:

**Persona Natural → Videoatención → Devoluciones**

El workflow de GitHub Actions ejecuta una comprobación cada 5 minutos. Si la DIAN deja de mostrar el mensaje:

`No se encontraron especialidades relacionadas según los filtros seleccionados.`

el monitor guarda una captura y envía una alerta por Telegram.

## Configuración requerida

En GitHub abre:

**Settings → Secrets and variables → Actions → New repository secret**

Crea estos dos secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Nunca pongas el token directamente en el código.

## Prueba manual

Ve a **Actions → DIAN Citas Monitor → Run workflow**.

Un resultado normal sin citas termina correctamente y muestra:

`RESULT: no availability`

Si hay posible disponibilidad, envía el mensaje de Telegram y adjunta una captura como artifact del workflow.

## Importante

El monitor solo avisa. No reserva citas automáticamente.

GitHub puede retrasar ocasionalmente los workflows programados, por lo que "cada 5 minutos" es el objetivo de programación, no una garantía de ejecución exacta al minuto.
