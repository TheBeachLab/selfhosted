# Asistente de Ingenieurbüro Francisco Sanchez Arroyo en ElevenAgents

## Edición y alcance

El titular solicitó el 15 de octubre de 2026 un agente común a sus marcas y
dominios, con identidad principal **Ingenieurbüro Francisco Sanchez Arroyo**.
Das Werklab es uno de los contextos que puede atender, no el nombre obligatorio
de toda llamada. La redacción y los conocimientos se mantienen directamente
en el panel de ElevenLabs; este repositorio no debe sobrescribirlos mediante
una sincronización automática.

- Agente: `agent_1701m4z3zdkeejct33cg2fwjhtnv`.
- [Editor del agente](https://elevenlabs.io/app/agents/agents/agent_1701m4z3zdkeejct33cg2fwjhtnv/agent).
- **Agent → System prompt**: identidad, tono y reglas de conversación.
- **Agent → First message**: saludo inicial.
- **Knowledge Base**: información de servicios, marcas y dominios.
- **Tools**: acciones reales, incluida la transferencia a Fran.

El guion elimina la cuota fija de palabras y las preguntas de seguimiento
obligatorias. Pide contestar directamente, presentarse una sola vez, conservar
el contexto tras interrupciones y preguntar por la marca solo cuando haga
falta. No permite inventar precios, disponibilidad ni compromisos. Los mensajes
internos se resumen en español.

## Estado de preparación

Agente creado en el panel; configuración preparada y pendiente de guardar.
El titular ha pedido expresamente no hacer pruebas hasta editarlo: no ejecutar
Preview, Test Connection, simulaciones ni llamadas de prueba por ahora.
Este agente no está conectado al número de Twilio. El servicio del NUC y la
ruta IE1 se mantienen independientes durante su preparación.

El primer intento de guardar fue rechazado por ElevenLabs: la voz Gesa Tess
(`cllvQaMvj0ZKxH88HGEn`) tiene `live moderation` y no se permite en agentes.
Ese mensaje se observó al publicar desde el panel el 15 de octubre de 2026;
no implica que su uso por la API de TTS del servicio actual del NUC falle.
La selección de una voz compatible queda pendiente.

### Horario de transferencias (15 de octubre, revisión posterior)

El titular aclaró que el asistente debe atender siempre. Solo las transferencias
a su móvil se limitan a lunes-viernes, 09:00–17:00, excluidos los festivos
aplicables en Múnich. Se preparó la herramienta `check_frans_availability` y se
actualizaron las instrucciones y condiciones de `transfer_to_number` para
consultarla inmediatamente antes de cada intento; ante error o resultado falso
deben continuar atendiendo sin transferir. La herramienta no ejecuta llamadas.
La regla de uso se configura en ElevenLabs; todavía no se ha validado su
cumplimiento con una conversación real.

El [servicio de horario](../services/francisco-hours/README.md) está desplegado
en el NUC desde el commit `9c204da`. La lectura pública de
`https://daswerklab.de/voice/business-hours` confirmó la hora `Europe/Berlin`
y `can_transfer` el 15 de octubre de 2026. Se verificaron por separado los
límites de horario, fines de semana, festivos móviles y locales, cambios de hora
y cambio de año mediante pruebas locales de calendario, sin llamadas ni LLM.
El servicio telefónico existente conservó su release `213209f` y su fecha de
arranque del 14 de octubre; no se modificó la ruta Twilio IE1.

En el borrador se conservó la voz **Ben – Effortless and Casual** elegida por
el titular, su nuevo saludo y su guion, limitando las modificaciones al horario
y a los nombres reales de herramientas. La plantilla incompleta de Workflow
se retiró: contenía una transferencia a otro agente sin destino y bloqueaba el
guardado. El agente vuelve al flujo de conversación normal con sus herramientas.

**Bloqueo de guardado observado en esta revisión:** el borrador local tiene
`llm=custom-llm` y `custom_llm=null`. Abrir el selector provoca un error del
cliente (`null.matchAll`) y publicar devuelve `Custom LLM must be defined`.
No se ha establecido qué campo exacto dispara la excepción de interfaz.
Architect indicó una reparación aplicada, pero la lectura posterior y el
rechazo del guardado no la confirmaron: su escritura quedó bloqueada por los
cambios locales aún sin sincronizar. No descartar ese borrador: contiene las
ediciones del titular. La versión remota sigue siendo la base `My Agent`.

La lectura de la API el 15 de octubre volvió a devolver HTTP 401,
`missing_permissions: convai_read`. Se ha solicitado autorización para ampliar
la clave existente `Fran Assistant` únicamente con lectura/escritura de
ElevenAgents y reparar el campo mediante API. La solicitud queda pendiente;
no se han cambiado permisos. La interfaz de permisos se dejó abierta en Safari.
El calendario está desplegado, pero la configuración nueva de atención y
transferencia de ElevenLabs aún no está publicada ni conectada al teléfono.

## Configuración preparada en el panel

- Alemán como idioma inicial, español e inglés adicionales. Saludos revisados
  manualmente; las traducciones automáticas antiguas quedan como metadatos,
  mientras los campos `overrides.agent.first_message` contienen los saludos
  corregidos.
- OpenAI con clave propia: `Custom LLM`, Chat Completions,
  `https://api.openai.com/v1`, modelo `gpt-6.1-sol`, razonamiento `low`, sin
  enviar temperatura. El titular añadió el secreto `OPENAI_API_KEY`; se ha
  comprobado su asociación visible, no su funcionamiento.
- TTS V4 Turbo; filtro de voces de fondo y términos de asentimiento en los
  tres idiomas para reducir interrupciones accidentales.
- Herramientas: fin de conversación, detección de idioma, ceder turno y
  transferencia al móvil fijo de Fran. No se han ejecutado transferencias.
- Análisis y resúmenes en español. No hay herramienta de envío de mensajes;
  el guion prohíbe afirmar un envío sin confirmación real.
- Acceso privado con autenticación; grabación de audio desactivada.
  Retención de transcripciones y datos derivados: siete días, con borrado al
  vencer. Esto difiere del servicio del NUC, que no guarda transcripciones
  completas, y debe tenerse presente antes de conectar clientes.
- Máximo de cuatro conversaciones simultáneas; bursting desactivado.

El panel es la fuente de configuración: los valores de esta sección describen
la preparación inicial y pueden cambiar cuando el titular edite el agente.
El guardado de configuración no acredita calidad de audio, latencia,
respuesta del modelo, comportamiento de herramientas ni compatibilidad de la
transferencia telefónica. Esas comprobaciones quedan pendientes por petición
del titular.

## Procedencia del contenido

La identidad común procede de la instrucción expresa del titular en esta
conversación. Los servicios de Das Werklab se contrastaron el 15 de octubre
de 2026 con [la página pública española](https://daswerklab.de/es/): consultoría
de ingeniería civil, dirección y coordinación de obra, sistemas y software.
Los demás dominios no tienen todavía fichas comerciales verificadas en este
agente; debe reconocer esa falta de información y recoger el motivo de la
consulta, sin atribuirles servicios por inferencia.

Referencias de configuración consultadas el 15 de octubre de 2026:

- [Guía inicial](https://elevenlabs.io/docs/eleven-agents/quickstart):
  campos de saludo e instrucciones y prueba desde el panel.
- [Guía de instrucciones](https://elevenlabs.io/docs/eleven-agents/best-practices/prompting-guide):
  el texto controla el comportamiento; idiomas y turnos se configuran aparte.
- [Base de conocimientos](https://elevenlabs.io/docs/eleven-agents/customization/knowledge-base):
  documentos de texto, archivos o URLs asociados al agente.
- [Transferencia a un número](https://elevenlabs.io/docs/eleven-agents/customization/tools/system-tools/transfer-to-number):
  las transferencias reales requieren un canal telefónico compatible.

La clave local de ElevenLabs tiene acceso a voces/TTS, pero la lectura de
agentes devolvió `missing_permissions: convai_read`. La creación se realiza
desde la sesión autenticada del panel, sin ampliar permisos de esa clave.
