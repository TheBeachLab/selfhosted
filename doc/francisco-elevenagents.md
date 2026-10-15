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
