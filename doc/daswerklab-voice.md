# Das Werklab: recepcionista de voz

Servicio propio en el Intel NUC, con Twilio Programmable Voice y OpenAI Realtime.
Las llamadas entran por el número 089 5104 2000 / +49 89 5104 2000.

## Comportamiento

- El asistente se identifica como IA, explica los servicios y conversa en
  español, inglés y alemán. El saludo empieza en alemán para clientes y en
  español cuando Fran llama desde su móvil configurado.
- Pedir hablar con Fran usa una herramienta con un destino fijo: el móvil
  profesional publicado, terminado en 0901. El modelo no puede elegir otro
  destino.
- Si el móvil está ocupado o no responde, vuelve al asistente y ofrece guardar
  un mensaje. El resumen se guarda en español después de que el cliente lo
  confirme. No se envían mensajes externos.
- DIRECT_CALLERS permite que números aceptados pasen directamente al móvil.
  Está vacío inicialmente: falta el número de Geier para identificarlo.
- La aplicación no guarda audio ni transcripciones completas. Los mensajes
  confirmados se guardan en SQLite con modo 0600, fuera del directorio web.
- Máximo inicial: cuatro conversaciones simultáneas y diez minutos por
  conversación con IA; la conexión al móvil tiene un límite de veinte minutos.

La información comercial está en
[knowledge.json](../services/daswerklab-voice/knowledge.json), comprobada contra
las tres páginas públicas de [Das Werklab](https://daswerklab.de/es/) el
14 de octubre de 2026. Incluye consultoría de ingeniería civil, coordinación de
obra, sistemas y software. Precios, citas, disponibilidad y habilitaciones se
remiten a Fran. El primer resultado en siete días requiere acordar alcance y
fecha de inicio; no es un plazo para terminar cualquier proyecto.

## Conexión y fuentes técnicas

Twilio llama a HTTPS /voice/incoming. La respuesta conecta una Media Stream
bidireccional a WSS /voice/media. El NUC conserva la configuración y las claves
y envía audio PCMU a OpenAI. No se requiere Asterisk para este flujo.

Al solicitar la transferencia, el servidor cierra la conexión de audio y Twilio
continúa en /voice/after-stream. La respuesta Dial llama al destino fijo. Si
no responde, /voice/dial-ended permite volver a la IA.

Fuentes oficiales consultadas el 14 de octubre de 2026:

- [Media Streams y mensajes WebSocket](https://www.twilio.com/docs/voice/media-streams/websocket-messages):
  audio mono μ-law a 8000 Hz; audio de salida, marcas de reproducción y clear.
- [Connect y Stream](https://www.twilio.com/docs/voice/twiml/stream):
  Connect bloquea las instrucciones siguientes hasta que el servidor cierra
  el WebSocket.
- [Dial](https://www.twilio.com/docs/voice/twiml/dial):
  conexión al móvil, callback de resultado, callerId y timeout.
- [Validación de firmas](https://www.twilio.com/docs/usage/security):
  validar X-Twilio-Signature tanto en webhooks como en el handshake WebSocket.
  La aplicación añade un ticket efímero vinculado a la llamada.
- [OpenAI Realtime por WebSocket](https://developers.openai.com/api/docs/guides/voice-websockets?api=realtime)
  y [sesiones y herramientas](https://developers.openai.com/api/docs/guides/realtime-conversations):
  esquema GA, audio PCMU, detección de turnos, interrupción y function calling.
- [Regiones de Twilio](https://www.twilio.com/docs/global-infrastructure/inbound-processing-api):
  cada región tiene su propia configuración de webhooks y credenciales;
  cambiar la región puede tardar cinco minutos en aplicarse.

## Preparación del NUC

El instalador solo admite una primera instalación y rechaza rutas, usuario o
puerto preexistentes. Preserva la web actual, añade una ubicación /voice/ y
valida Nginx antes de recargarlo. El proceso escucha en 127.0.0.1:18090 y se
ejecuta como usuario dedicado con límites de recursos y directorios protegidos.

Los archivos de servicio están en
[services/daswerklab-voice](../services/daswerklab-voice/).
La configuración privada se mantiene en /etc/daswerklab-voice.env, root:root,
modo 0600. Las variables disponibles están documentadas en .env.example.
La instalación no crea claves de OpenAI ni activa el número de Twilio.

Después de integrar los cambios en master, copiar los archivos de servicio
desde ese commit a una carpeta temporal privada del NUC. Ejecutar allí:

~~~sh
sudo python3 install.py --revision COMMIT_INTEGRADO
~~~

El informe /var/lib/daswerklab-voice/installation.json registra los hashes de
los archivos y del vhost anterior/posterior. /opt/daswerklab-voice/website.before
preserva la configuración web previa.

Sin clave de OpenAI, /voice/healthz devuelve HTTP 503 y ready=false. Al disponer
de la clave, reiniciar daswerklab-voice: el arranque verifica la configuración
de Realtime, sin generar audio. Esta comprobación no sustituye una llamada real.

## Activación de Twilio

Observación directa del 14 de octubre de 2026: el número está contratado y su
región activa es IE1. Las credenciales locales funcionan para US1; la petición
equivalente a IE1 devuelve HTTP 401. El webhook US1 está vacío. No asumir que
cambiar un webhook US1 conecta las llamadas entrantes de IE1.

El script configure_twilio.py es de solo lectura por defecto. Para activar,
exige que el servicio responda ready=true, un archivo de recibo nuevo y
credenciales válidas para la región seleccionada. Una migración de región
necesita explícitamente --allow-region-change. Las configuraciones anteriores
se guardan en el recibo antes de modificarlas.

Opciones: conservar IE1 y proporcionar su clave, secreto y Auth Token
regionales; o usar US1 con las credenciales ya configuradas y migrar el número.
El Auth Token del servicio debe corresponder a la región de las llamadas.

~~~sh
python3 configure_twilio.py --region us1
python3 configure_twilio.py --activate --region us1 --allow-region-change \
  --receipt RUTA_PRIVADA_NUEVA.json
~~~

Verificar después una llamada al número contratado y su registro en la región
activa. Probar información de servicios y cambios de idioma. Probar la
transferencia desde otro teléfono para poder contestar en el móvil de Fran.
Las pruebas simuladas no demuestran el comportamiento del modelo con voz real
ni la conexión de telefonía.

## Pruebas y mensajes

Usar un entorno Python 3.10+ independiente:

~~~sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m unittest -v test_server
~~~

Las pruebas cubren firmas y cuentas, tickets de llamada, audio PCMU,
interrupciones, transferencia al destino fijo, retorno si no responde,
mensajes idempotentes y privados y rechazo de transferencias a otros números.

Mensajes locales: /var/lib/daswerklab-voice/messages.sqlite, tabla messages.
Contiene fecha, nombre/contacto proporcionado, idioma y summary_es.
No existe un endpoint público que los liste.
