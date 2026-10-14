# Das Werklab: recepcionista de voz

Servicio propio en el Intel NUC, con Twilio Programmable Voice y OpenAI Realtime.
Las llamadas entran por el número 089 5104 2000 / +49 89 5104 2000.

## Estado verificado: 14 de octubre de 2026

La implementación bc4219daf531776df82e556fc9bb6fe0c3a48291 está integrada en
master e instalada en el NUC. El servicio está activo y Nginx pasa su validación.
El recibo update-bc4219daf531776df82e556fc9bb6fe0c3a48291.json, en
/var/lib/daswerklab-voice/, registra ese commit y los hashes de los archivos.
installation.json conserva el registro de la instalación inicial 8fc528d.

Las llamadas están configuradas para entrar al agente. La clave de OpenAI
está instalada en la configuración privada del NUC y el endpoint HTTPS
/voice/healthz devuelve 200 con ready=true. El servicio está activo sin
reinicios inesperados tras instalar la clave.

La lectura de las API de Twilio confirma la región activa Ireland (IE1), VoiceUrl
https://daswerklab.de/voice/incoming y StatusCallback
https://daswerklab.de/voice/status, ambos con método POST. Alemania tiene
una prueba de salida completada desde IE1 al propio número alemán de Twilio.
El NUC valida las firmas con el Auth Token de IE1. Mantener el número en
Irlanda: no migrar a US1 para utilizar otras credenciales. Los recibos privados
conservan los estados anteriores y posteriores en
/Users/Papi/.config/recepcionista/.

Validación realizada:

- 25 pruebas simuladas pasan en Python 3.10, también sobre master.
- El webhook HTTPS rechaza peticiones sin firma con 403.
- OpenAI Realtime completa respuestas con audio PCMU sobre los servicios en
  español, inglés y alemán. En los tres idiomas selecciona transfer_to_fran
  con el idioma correcto al solicitar hablar con Fran.
- Una llamada sintética firmada recorre HTTPS, WSS y el modelo real: recibe
  el saludo, procesa audio PCMU con la frase «Pásame a Fran, por favor» y
  devuelve un Dial al móvil fijo. El callback sintético no-answer vuelve a
  la IA con un ticket nuevo. El contexto sintético se elimina al terminar.
- El handshake WSS sin firma devuelve 403.
- La configuración privada y la base de mensajes tienen permisos 0600.
- Las páginas públicas española, inglesa y alemana continúan devolviendo 200.
- Una llamada de prueba creada en IE1 al propio número de Twilio completa
  sus dos tramos (saliente y entrante) durante ocho segundos; el NUC acepta
  su Media Stream. No se llamó al móvil de Fran. El recibo es
  /Users/Papi/.config/recepcionista/twilio-selftest-ie1-20261014.json.
- Los archivos desplegados coinciden por SHA-256 con el commit integrado.
  La voz configurada es Cedar, con respuestas de audio verificadas en los
  tres idiomas.
- Bridge.run, ejecutado desde el código desplegado con el modelo real, genera
  el saludo alemán «Hallo! Ich bin Frans virtueller Assistent bei Das Werklab».
  Después reconoce «Hola, pásame a Fran» y selecciona transfer_to_fran en
  español. La petición del saludo incluye explícitamente de-DE: las
  instrucciones de respuesta sustituyen las instrucciones de sesión, según
  la [referencia de OpenAI](https://developers.openai.com/api/reference/resources/realtime/client-events).

Estas verificaciones consumieron audio de OpenAI y una llamada interna de
Twilio al número propio. Queda pendiente la prueba humana desde un teléfono
externo: escucha, conversación y transferencia que haga sonar el móvil de Fran.
El anuncio de indisponibilidad comunicado en el primer intento humano no tuvo
un registro entrante visible en US1; no se estableció su causa. La prueba
interna completada en IE1 no demuestra por sí sola la recepción desde fraenk
ni la transferencia al móvil.

## Comportamiento

- El asistente se identifica como Asistente de Fran, explica los servicios y conversa en
  español, inglés y alemán. El saludo empieza en alemán para clientes.
- Usa Cedar y se presenta como asistente virtual de Fran. Cove no figura entre
  las voces de [Realtime](https://developers.openai.com/api/docs/guides/realtime-conversations),
  comprobado el 14 de octubre de 2026; el titular eligió Cedar.
- Pedir hablar con Fran usa una herramienta con un destino fijo: el móvil
  profesional publicado, terminado en 0901. El modelo no puede elegir otro
  destino.
- Si el móvil está ocupado o no responde, vuelve al asistente y ofrece dejar
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
- [Credenciales regionales](https://www.twilio.com/docs/global-infrastructure/manage-regional-api-credentials):
  un Auth Token o una API key solo funciona en la región donde fue creado.
  IE1 requiere su token para las firmas y permite autenticar la REST API con
  Account SID y ese mismo token.
- [Permisos por país](https://www.twilio.com/docs/voice/api/dialingpermissions-country-resource)
  y [actualización de permisos](https://www.twilio.com/docs/voice/api/dialingpermissions-bulkcountryupdate-resource):
  la lectura de Countries/DE comprueba los tres permisos; BulkCountryUpdates
  permite habilitar llamadas normales solo para DE conservando los otros dos.

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

Observación directa del 14 de octubre de 2026: el número está activo en IE1,
con los dos webhooks POST configurados en esa región. Las credenciales US1
devolvían HTTP 401 en IE1. Tras guardar TWILIO_IE1_AUTH_TOKEN en el archivo
local privado, la API de Irlanda autenticó correctamente. El token regional
se instaló como TWILIO_AUTH_TOKEN en /etc/daswerklab-voice.env.

El script configure_twilio.py es de solo lectura por defecto. Para activar,
exige que el servicio responda ready=true, un archivo de recibo nuevo y
credenciales válidas para la región seleccionada. Una migración de región
necesita explícitamente --allow-region-change. Las configuraciones anteriores
se guardan en el recibo antes de modificarlas.

La instalación actual usa IE1 y su Auth Token para validar las firmas. El script
prefiere TWILIO_IE1_API_KEY y TWILIO_IE1_API_SECRET si están disponibles; en su
ausencia admite Account SID y TWILIO_IE1_AUTH_TOKEN. No utiliza el token de US1
como sustituto del de Irlanda. Las credenciales US1 locales solo permiten
consultar el control de enrutamiento; no determinan la región de las llamadas.

~~~sh
python3 configure_twilio.py --region ie1
python3 configure_twilio.py --activate --region ie1 \
  --receipt RUTA_PRIVADA_NUEVA.json
~~~

Recibo de esta activación:
/Users/Papi/.config/recepcionista/activation-20261014-ie1.json.
La restauración del número a Irlanda se conserva en
/Users/Papi/.config/recepcionista/ireland-region-restore-20261014.json.
La API voice.twilio.com confirmó el permiso DE de llamadas normales habilitado
y los dos permisos de alto riesgo deshabilitados; su recibo se conserva en
/Users/Papi/.config/recepcionista/germany-dialing-permission-20261014.json.
La consulta equivalente a voice.dublin.ie1.twilio.com devolvió HTTP 404, por lo
que no se presenta esa lectura de permisos como una verificación regional IE1.
La salida real de prueba desde IE1 al número propio sí se completó.

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
