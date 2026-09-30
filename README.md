# DIAN Citas Monitor

Monitor gratuito para comprobar disponibilidad de **Persona Natural > Videoatención > Devoluciones** en el portal de agendamiento de la DIAN.

## Cómo funciona

GitHub Actions ejecuta una comprobación programada. El script:

1. Abre `https://agendamiento.dian.gov.co/`.
2. Entra a **Agendar cita**.
3. Selecciona **Persona Natural**.
4. Selecciona **Videoatención**.
5. Selecciona **Devoluciones.**
6. Si aparece exactamente:
   `No se encontraron especialidades relacionadas según los filtros seleccionados.`
   termina sin enviar alerta.
7. Si el flujo llegó correctamente a Devoluciones y ese mensaje no aparece, guarda una captura y envía una alerta por Telegram.

El monitor **no reserva citas automáticamente**.

## Secrets requeridos

En GitHub abre:

`Settings > Secrets and variables > Actions > New repository secret`

Crea:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Nunca guardes esos valores directamente en el código.

## Ejecución manual

En la pestaña **Actions**, abre **DIAN Citas Monitor** y usa **Run workflow**.

## Programación

El workflow está configurado con cron cada 5 minutos. GitHub Actions puede iniciar ejecuciones programadas con retraso ocasional dependiendo de la carga de los runners.
