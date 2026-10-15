# Horario de transferencia a Fran

El asistente atiende siempre. Antes de transferir al móvil consulta
`GET https://daswerklab.de/voice/business-hours`, sin parámetros ni credenciales.
Solo permite la transferencia si `can_transfer` es `true`; cualquier error o
resultado ausente se trata como no disponible. La decisión se consulta de nuevo
para cada intento, no se reutiliza al principio de una llamada larga.

Regla indicada por el titular el 15 de octubre de 2026: lunes a viernes,
09:00 inclusive a 17:00 exclusive, zona `Europe/Berlin`, excluidos los festivos
de Bayern aplicables en Múnich. Incluye Mariä Himmelfahrt; no incluye el
Friedensfest exclusivo de Augsburgo. Nochebuena y Nochevieja no son festivos
adicionales en esta configuración. Los festivos se calculan cada año, sin una
tabla que caduque; cambios legales futuros requieren revisar la lista.

Fuentes consultadas el 15 de octubre de 2026:
- [Ministerio del Interior de Bayern](https://www.stmi.bayern.de/staat-und-verfassung/feiertage/).
- [Calendario de Múnich](https://www.muenchen.de/aktuell/feiertage-bayern-2026-und-2027).

Servicio independiente, Python estándar, solo escucha en localhost:18092.
No accede a claves, conversaciones ni al servicio telefónico. Nginx expone
únicamente esta consulta pública de horario, sin registrar solicitudes ni
cachear resultados. El despliegue no cambia Twilio/IE1 ni reinicia el servicio
`daswerklab-voice`. Code Tools de ElevenLabs requiere Enterprise según
[su documentación](https://elevenlabs.io/docs/eleven-agents/customization/tools/code-tools);
por eso esta consulta usa el NUC existente.

Tras integrar en master, copiar esta carpeta al NUC y ejecutar como root
`python3 install.py --revision <SHA integrado>`. El instalador inicial rechaza
instalaciones ya existentes y guarda el vhost anterior para recuperación.
La comprobación local del calendario es independiente del agente:
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s services/francisco-hours`.
No ejecuta LLM, audio, simulaciones ni llamadas.
