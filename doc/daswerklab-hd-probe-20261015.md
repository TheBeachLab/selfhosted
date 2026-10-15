# Prueba aislada de Media Streams HD en Irlanda

Comprobada el 15 de octubre de 2026, entre 07:18 y 07:20 Europe/Madrid.
El [recibo resumido](evidence/daswerklab-hd-ie1-20261015.json) conserva los
atributos solicitados, el formato recibido y las advertencias de Twilio.

## Resultado observado

Las cinco conexiones recibieron audio real, mono, `audio/x-mulaw` a 8000 Hz.
Solicitar `sampleRate="16000"` no cambió el formato recibido. Twilio emitió
advertencias XML 12200 que indican que `audioFormat` y `sampleRate` no están
permitidos en `Stream`. La solicitud se continuó con el formato estándar.

| Caso | audioFormat solicitado | sampleRate solicitado | Audio recibido |
| --- | --- | --- | --- |
| Control estándar | omitido | omitido | μ-law, 8000 Hz, mono |
| Control inválido | hd_probe_invalid | 12345 | μ-law, 8000 Hz, mono |
| Solicitud L16 | audio/x-l16 | 16000 | μ-law, 8000 Hz, mono |
| Solicitud PCM | pcm | 16000 | μ-law, 8000 Hz, mono |
| Solicitud PCM16 | pcm16 | 16000 | μ-law, 8000 Hz, mono |

Los valores experimentales de `audioFormat` no se presentan como valores
oficialmente admitidos: el SDK tipa el campo como cadena y no documenta sus
valores. La advertencia del servidor se refiere al atributo, con independencia
de su valor. El control deliberadamente inválido también se continuó a 8000 Hz.

Esto demuestra que estos nuevos atributos no habilitaron HD en la interfaz
`Connect/Stream`, cuenta y región IE1 probadas. No establece la disponibilidad
en otras cuentas, regiones, programas privados, SIP u otros transportes. Tampoco
prueba el recorrido de una llamada PSTN alemana: no se llamó a ningún teléfono.

## Aislamiento y evidencia

- Se crearon llamadas REST únicamente a una identidad temporal `client:hd-probe-*`.
  El número contratado se usó como identificador de origen, sin recibir llamadas.
- El cliente utilizó tonos sintéticos a 1000, 5500 y 6500 Hz; no se solicitó el
  micrófono. El AudioContext funcionó a 48000 Hz y WebRTC negoció Opus con reloj
  RTP de 48000 Hz. Un reloj RTP de 48000 no demuestra por sí solo banda ancha
  de extremo a extremo; el formato recibido por el receptor es el resultado
  que se compara en esta prueba.
- El receptor WebSocket temporal estuvo fuera del NUC, detrás de un Quick
  Tunnel. Validó firmas de Twilio y aceptó únicamente llamadas creadas por el
  experimento. La página local y el endpoint del token estuvieron en otro puerto
  de loopback, sin publicarse por el túnel. Las comprobaciones externas de esas
  rutas devolvieron 404 y el stream sin firma devolvió 403.
- Una primera tanda tuvo un error en la validación del esquema de URL de la
  firma WSS. No se usó para concluir sobre audio. Se corrigió el receptor,
  manteniendo validación de firmas HTTPS/WSS, y se repitió con control estándar
  válido y audio recibido en los cinco casos. Se crearon diez llamadas de
  laboratorio en total; las cinco de la tanda válida duraron doce segundos cada una.
- No se utilizaron OpenAI ni ElevenLabs, ni se desplegó código en el NUC.
  La configuración del número y su región IE1 coinciden exactamente antes y
  después. El proceso de producción mantuvo PID 3743756, cero reinicios y la
  versión `213209f6e98d76206cea4cbe40a2ca67e461314b`; healthz devolvió ready=true.
- Se verificó que las diez llamadas terminaron, que no quedaron claves
  temporales, que el túnel y ambos listeners locales estaban cerrados, y que el
  cliente WebRTC se destruyó. No se guardó audio: solo metadatos y mediciones.
- Twilio todavía no había informado del precio de varias llamadas al terminar
  la auditoría. El recibo no convierte importes ausentes en cero ni presenta
  un coste exacto no facturado.

Los recibos completos de ambos intentos y la auditoría de recursos están en
`/Users/Papi/.config/recepcionista/hd-probe-20261015/`, con acceso del propietario.
Los identificadores y direcciones efímeras no se incluyen en el recibo versionado.

## Repetición del experimento

La utilidad de laboratorio es
[hd_probe.py](../services/daswerklab-voice/hd_probe.py), con
[cliente sintético](../services/daswerklab-voice/hd_probe.html) y
[dependencias separadas](../services/daswerklab-voice/requirements-hd-probe.txt).
No forma parte del arranque ni de las dependencias del recepcionista.

1. Preparar un directorio privado de ejecución con `cloudflared`, el bundle
   `twilio.min.js` de `@twilio/voice-sdk` y `dependencies.json` con versiones/hashes.
   Instalar las dependencias Python en un entorno virtual separado.
2. Ejecutar `hd_probe.py --runtime <directorio> --cloudflared <binario>`.
   La configuración regional se lee del archivo privado existente. La utilidad
   comprueba IE1, crea una clave temporal y un token de solo recepción de quince
   minutos. No crea un TwiML App, ni actualiza números, rutas o webhooks.
3. Abrir la URL local mostrada y pulsar «Iniciar cliente de prueba».
   Se crean como máximo cinco llamadas, cada una con límite de doce segundos,
   siempre a la identidad temporal. Si falla el audio del control estándar, se
   interrumpe la tanda sin interpretar los resultados HD.
4. Revisar `report.json`: exigir `tests_finished=true`, configuración idéntica
   y clave temporal eliminada. La salida o una señal normal detiene las llamadas
   del experimento, revoca su clave y cierra el túnel. Ante pérdida del proceso,
   `private-state.json` conserva el SID de la clave para su limpieza; su secreto
   no se persiste. El límite temporal de las llamadas sigue siendo de doce segundos.

Las pruebas locales de firmas y limpieza se ejecutan desde el directorio del
servicio con `python -m unittest -v test_hd_probe`. No realizan peticiones a Twilio.

## Fuentes oficiales, comprobadas el 15 de octubre de 2026

- [Cambios de Twilio SDK](https://github.com/twilio/twilio-oai/blob/main/CHANGES.md):
  el cambio del 28 de septiembre de 2026 añadió `audio_format` y `sample_rate` a
  Stream. Su presencia en el SDK motivó el experimento; no acredita disponibilidad
  de servidor.
- [Código del SDK](https://github.com/twilio/twilio-node/blob/main/src/twiml/VoiceResponse.ts):
  los atributos XML se llaman `audioFormat` y `sampleRate`.
- [Mensajes de Media Streams](https://www.twilio.com/docs/voice/media-streams/websocket-messages):
  `start.mediaFormat` indica el formato efectivo y la documentación pública
  especifica μ-law a 8000 Hz.
- [XML Validation warning 12200](https://www.twilio.com/docs/api/errors/12200):
  significado de las advertencias obtenidas en las llamadas reales.
- [Voice JavaScript SDK](https://www.twilio.com/docs/voice/sdks/javascript/twiliodevice)
  y su [changelog](https://github.com/twilio/twilio-voice.js/blob/master/CHANGELOG.md):
  opciones `getUserMedia`, `enumerateDevices`, codecPreferences y soporte regional.
- [Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/):
  endpoint temporal para desarrollo; desaparece al detener cloudflared.
