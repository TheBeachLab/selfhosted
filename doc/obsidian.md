# Obsidian: notes, links and Canvas

**Author:** Fran
**Checked:** 2026-10-02

Obsidian está instalado en el Mac (`1.13.7`). En la inspección acotada del NUC no
se detectó la aplicación ni un contenedor o servicio. Ver el
[inventario y la arquitectura](knowledge-graphs.md).

## Qué uso para cada cosa

Las notas son archivos Markdown. Un enlace `[[Decisión]]` conecta notas y aparece
en Graph view. Canvas permite colocar notas y tarjetas, dibujar conexiones y
organizar el mapa manualmente; guarda un archivo `.canvas`.
[Graph view](https://help.obsidian.md/plugins/graph) y
[Canvas](https://help.obsidian.md/plugins/canvas), consultados el 2026-10-02.

```markdown
# Decisión de arquitectura

Fuente: documento original, revisión y fecha.
Estado: propuesta / confirmado con evidencia.

Usar [[LangGraph]] para el flujo y [[Graphiti]] para la memoria temporal.
```

El grafo de notas representa enlaces entre documentos. Los grafos de ejecución
y las relaciones de Neo4j se mantienen mediante sus propias herramientas.

En el piloto del Mac:

```text
/Users/Papi/Repositories/project-knowledge/vaults/strategy/
/Users/Papi/Repositories/project-knowledge/vaults/hariburi/
```

Las notas `Inicio`, `Decisiones` y `Reuniones` son editables. `Fuentes/` contiene
vistas generadas; corregir el original y después ejecutar el indexador del
piloto. Es el contrato descrito en su `AGENTS.md`, README y código, comprobados
el 2026-10-02. No copiar esas vistas como si fueran fuentes verificadas.

## Obsidian en el NUC, si necesito usarlo desde el navegador

La opción de [LinuxServer](https://docs.linuxserver.io/images/docker-obsidian/)
ejecuta la aplicación mediante un escritorio remoto. Persiste configuración y
archivos en `/config`, y ofrece HTTPS en el puerto interno 3001. La imagen
incluye capacidades de escritorio y terminal; hay que restringir el acceso y
los montajes. Fuente consultada el 2026-10-02.

Configuración propuesta, pendiente de desplegar y probar:

- Imagen `lscr.io/linuxserver/obsidian`, fijada a un digest al instalar.
- Configuración propia en `/srv/obsidian/config/`; vault explícito y distinto
  del perfil. No montar el home entero ni el socket Docker.
- Puerto del host propuesto `127.0.0.1:18888` hacia el HTTPS interno 3001.
  Comprobar que siga libre. Los puertos 3000 y 3001 del host ya estaban ocupados.
- Arranque bajo demanda, sin habilitar la eGPU. Probar un límite inicial de
  2 GiB y dos CPU; ajustar según uso real.
- Acceso inicial por túnel:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:18888:127.0.0.1:18888 pink-sudo
```

Después de desplegar, abrir `https://127.0.0.1:18888/`. El certificado interno
es autofirmado; el acceso público requiere TLS y autenticación propios según
[Authentik](authentik.md), además de una prueba de WebSocket.

Antes de darlo por operativo: crear una nota y un Canvas de prueba, reiniciar,
confirmar persistencia y probar una copia/restauración del vault y `/config`.
El contenedor, la sincronización Mac–NUC y el acceso web no están configurados
por esta guía. Elegir dónde vive el vault original antes de habilitar escritores
en más de un equipo.
