# Guía corta de demostración y entrega — Proyecto 2

## Preparación

1. Abre `iniciar_windows.bat` en Windows o `./iniciar_linux_mac.sh` en macOS/Linux. También puedes utilizar `python iniciar.py`.
2. Abre `pruebas_tac/17_clases.cps` desde el IDE y pulsa **F5**. Observa `class`, inicialización de campos, `new`, constructor, métodos y la tabla de símbolos con sus offsets.
3. Abre `pruebas_tac/16_recursion.cps` y pulsa F5. Explica la sección `func`, `param`, `call`, `return` y los registros de activación por invocación.
4. Abre `pruebas_tac/12_foreach.cps` o `13_switch_entero.cps` y enseña etiquetas, saltos, `break`/`continue` y traducción de condiciones.
5. Abre `pruebas_tac/21_operacion_reciclaje.cps` y muestra los nombres temporales repetidos y el contador de reutilizaciones.
6. Abre `pruebas_tac/25_errores_multiples.cps` y demuestra que aparecen **tres diagnósticos** y que la pestaña TAC queda **vacía**.
7. Abre `pruebas_regresion/01_for_sin_condicion.cps` y `05_try_anidados.cps` para mostrar los casos recuperados. Después, `06_expresion_con_mutacion.cps` para mostrar una copia temporal que conserva el valor del primer operando. Pulsa **A+**, **A−**, cambia el tema y usa **Exportar .tac** con un caso correcto.
8. Ejecuta `verificar_windows.bat` o `python verificar_proyecto.py` y muestra el resumen de **138 verificaciones automáticas**.

## Documentación

- `README.md`: instalación, manejo del IDE, comandos, pruebas y archivos.
- `DOCUMENTACION_TAC.md`: especificación del TAC e instrucciones, ejemplos y supuestos.
- `DOCUMENTACION_ARQUITECTURA.md`: diseño del compilador, etapas, tabla de símbolos y frames.
- `verificar_proyecto.py`: batería automatizada reproducible de semántica, recuperación, TAC, tabla de símbolos y regresiones.

9. Si la máquina tiene entorno gráfico disponible, `python verificar_interfaz.py` ejecuta **11 comprobaciones** de la GUI.

## Publicación en GitHub

La especificación del proyecto exige un repositorio y participación **real** y diferenciable de los integrantes en los commits. El ZIP no publica automáticamente código ni inventa el historial. Creen o usen su repositorio, revisen los cambios y hagan commits de las contribuciones que haya realizado cada persona. Documenten las pruebas y preparen una demostración desde la interfaz, no solo desde consola.

## Alcance

El programa es un **compilador frontal con TAC abstracto**, no una máquina virtual. No ejecuta Compiscript, no produce assembler ni código objeto y no busca reportar todas las cascadas de errores provocadas por una entrada inválida.

