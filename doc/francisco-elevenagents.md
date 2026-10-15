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

Configuración publicada y leída de nuevo por API el 15 de octubre de 2026,
versión `agtvrsn_4901m4zw9qnveenafn6w7aa5gp4k`. El guardado ya no devuelve
`Custom LLM must be defined`; el formulario de OpenAI vuelve a abrir.
Esto acredita la configuración guardada, no una respuesta correcta del LLM.
El titular ha pedido expresamente no hacer pruebas hasta editarlo: no ejecutar
Preview, Test Connection, simulaciones ni llamadas de prueba por ahora.
Este agente no está conectado al número de Twilio. El servicio del NUC y la
ruta IE1 se mantienen independientes durante su preparación.

El primer intento de guardar fue rechazado por ElevenLabs: la voz Gesa Tess
(`cllvQaMvj0ZKxH88HGEn`) tiene `live moderation` y no se permite en agentes.
Ese mensaje se observó al publicar desde el panel el 15 de octubre de 2026;
no implica que su uso por la API de TTS del servicio actual del NUC falle.
Posteriormente, el titular eligió **Ben – Effortless and Casual**
(`aTTiK3YzK3dXETpuDE2h`); ElevenLabs aceptó el guardado con esa voz.

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

### Reparación y lectura posterior (15 de octubre)

El borrador tenía `llm=custom-llm` con `custom_llm=null`. El panel fallaba al
abrirlo (`null.matchAll`) y el guardado rechazaba la conexión vacía. Tras la
autorización expresa del titular, se amplió la clave existente `Fran Assistant`
con **ElevenAgents Write** (incluye lectura), manteniendo los demás permisos.
Las operaciones oficiales GET y PATCH de Agents devolvieron HTTP 200.

Se reparó el objeto Custom LLM por API. Inicialmente el panel mostró la versión
base `My Agent`; **Sync Now** recuperó el borrador con las ediciones del titular
y combinó la conexión reparada. No se descartó el borrador. La acción **Copy
agent JSON config** exportó la versión publicada, no las ediciones pendientes;
no debe usarse como prueba de respaldo de un borrador sin comparar su contenido.
Se publicó el borrador recuperado desde **Review Changes** y después se leyó
la versión completa mediante GET. La copia privada de recuperación está en
`~/.config/recepcionista/eleven-repair-20261015/published-final.json` (0600).
No almacenar claves ni exportaciones privadas en Git.

La lectura posterior confirmó nombre, guion de 5.341 caracteres, Ben,
alemán/español/inglés, saludos del titular, base de conocimientos, zona
Europe/Berlin, autenticación privada, audio sin grabación y retención de siete
días. La API de secretos confirmó que la referencia del modelo corresponde al
secreto existente `OPENAI_API_KEY`; no se creó ni sustituyó ninguna clave.
El endpoint, modelo y secreto están configurados; no se ha ejecutado una
inferencia ni se ha probado la validez de la clave frente al modelo.

El procedimiento anterior **Transfer Call** tenía una condición inferida por
LLM con cierre a las 18:00 y pasos que solo hablaban: no ejecutaba la consulta
de horario ni la transferencia. Se reemplazó en el borrador por un procedimiento
editable de texto, con referencias explícitas a la herramienta de horario y a
`transfer_to_number`; el original permanece recuperable en la versión anterior.
La API no permite cambiar el tipo de un procedimiento existente, por lo que
se creó el reemplazo y se retiró el anterior del conjunto de trabajo del
borrador, antes de publicar ambos cambios juntos.

- Procedimiento vigente: `agtprc_7401m4zw7wmpeyj89r1psk19atkk`.
- Herramienta de horario: `tool_4901m4zsr177emrtg0x9j09579ra`, GET al servicio
  del NUC, sin parámetros, con `can_transfer` asignado conservando tipo a
  `is_business_hours`.
- Las instrucciones, el procedimiento y la condición de transferencia exigen
  una consulta nueva y satisfactoria antes de cada intento. Ante error o
  `false`, el asistente sigue atendiendo. Es una regla de uso del agente;
  todavía no se ha probado su cumplimiento conversacional ni es un bloqueo
  del operador telefónico.
- Workflow guardado: solo nodo inicial, sin la plantilla incompleta.
- La respuesta GET contiene `phone_numbers=[]`: este agente aún no atiende el
  número de Twilio. No se modificó la ruta IE1 ni se reinició el servicio de voz.

No se ejecutaron Preview, Test Connection, simulaciones, audio ni llamadas.
La siguiente validación de conversación queda pendiente de autorización del
titular tras revisar el agente.

## Configuración guardada en el panel

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
la lectura posterior al guardado y pueden cambiar cuando el titular edite el agente.
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

- [Actualizar un agente](https://elevenlabs.io/docs/api-reference/agents/update):
  reparación parcial del objeto Custom LLM, seguida de lectura GET.
- [Procedimientos de texto](https://elevenlabs.io/docs/eleven-agents/customization/procedures/free-form-procedures):
  referencias `[tool id="..."]` y `[system_tool id="transfer_to_number"]`.
- [Procedimientos estructurados](https://elevenlabs.io/docs/eleven-agents/customization/procedures/structured-procedures):
  los pasos Tell no pueden ejecutar herramientas; solo los pasos Tool pueden.

La autorización de lectura/escritura de Agents ya se aplicó a la clave existente;
las restricciones de no realizar pruebas y no cambiar la ruta telefónica
siguen vigentes.
