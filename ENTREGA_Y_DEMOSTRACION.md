# Guion de demostración — Proyecto 3 (generación de código MIPS)

Duración sugerida: 15 minutos. Todos los archivos están en `pruebas_mips/` y se pueden cargar desde el botón **Pruebas** del IDE (doble clic → F5 → F6).

## Preparación (antes de la presentación)

1. `python iniciar.py` (o `iniciar_windows.bat`) y verificar que el IDE abra.
2. `python verificar_proyecto.py` → debe terminar con **197/197**.
3. Si la máquina tiene Java: `python verificar_mips.py --externo` → los programas válidos dan la misma salida en MARS y SPIM.

## Recorrido por la rúbrica

| Paso | Archivo | Qué mostrar | Rúbrica |
| --- | --- | --- | --- |
| 1 | `00_programa_ejemplo.cps` | F5 → pestaña **MIPS** (vtables, cadenas, prólogo de `main`). F6 → **Ejecución**. **Comparar MARS/SPIM** → «salida idéntica». **Exportar .asm** y abrirlo en MARS (**Abrir MARS**, F3, F5). | Uso de simulador (1) |
| 2 | `19_arbol_activacion.cps` | F6 → **Activación**: árbol de `fib(4)` con argumentos y retornos. | Árboles de activación (5) |
| 3 | `13_recursion.cps` | **MIPS**: prólogo/epílogo de `fn_factorial` (reserva del marco, `$ra`, `$fp`, `$s0` preservado). **Registros**: marco de cada función. **Activación**: profundidad 11 en Ackermann/factorial. | Registros de activación (5), recursividad (2) |
| 4 | `12_funciones_parametros.cps` | Función `seis` con 6 parámetros: los dos últimos viajan por la pila (`lw $s4, 0($fp)`), los cuatro primeros en `$a0`–`$a3`. | Funciones y parámetros (2) |
| 5 | `14_closures.cps` | Funciones anidadas: enlace de acceso en `-12($fp)` y doble salto `lw $t8, -12($t8)` en `nivel3`. | Registros de activación (5) |
| 6 | `18_presion_registros.cps` | **Registros**: 8 derrames, 8 `$t` ocupados, 26 reutilizaciones, temporales guardados antes de llamadas. En el `.asm` sin optimizar (desmarcar la casilla) buscar «derrame (spill)». | Selección de registros (4) |
| 7 | `01`–`05` | Variables/constantes, aritmética (división truncada, desbordamiento de 32 bits), lógica con cortocircuito (contador de llamadas), cadenas y arreglos 1D/2D con verificación de límites. | 1 + 1 + 1 + 1 |
| 8 | `06`–`11` | if/else, while, do-while, for, foreach, switch (caída, break, default, string) y ternario. | Control (3) |
| 9 | `15_clases_objetos.cps` | Objetos con constructor, inicializadores, `this`, miembros sin `this`, objetos en arreglos. | Clases y objetos (2) |
| 10 | `16_herencia.cps` | Tablas `vt_Animal` / `vt_Cachorro` (mismo índice para `hablar`), despacho con `jalr`, polimorfismo (`mascota: Animal`). En **Activación**: `Animal.presentar` llama a `Cachorro.hablar`. | Herencia (2) |
| 11 | `17_try_catch.cps` | Índice fuera de rango, división entre cero, nulo, error dentro de una recursión (en **Activación** las llamadas aparecen «terminada por una excepción»), try anidados y break/continue/return dentro de try. | try/catch (2) |
| 12 | `20_error_no_capturado.cps` | Caso fallido: mensaje y **código 1** (también en MARS/SPIM). | try/catch (2) |
| 13 | cualquier programa | Pestaña **Mirilla**: tabla de las 11 transformaciones y el detalle antes/después. Desmarcar la casilla para comparar el número de instrucciones. | Mirilla (3) |
| 14 | `23_*`, `24_*`, `25_*` | Casos fallidos de compilación: diagnósticos semánticos/sintácticos sin MIPS; `MIPS_UNSUPPORTED` del backend. | Batería de pruebas |
| 15 | consola | `python verificar_proyecto.py` y `python compilar_cli.py pruebas_mips/19_arbol_activacion.cps -e --arbol --mars --spim`. | Batería de pruebas |

## Documentación entregada

* `README.md`: instalación, uso del IDE y de la consola, simuladores, pruebas.
* `DOCUMENTACION_ARQUITECTURA.md`: arquitectura de todo el compilador.
* `DOCUMENTACION_MIPS.md`: backend MIPS (marcos, getReg, traducciones, runtime, try/catch, mirilla, simulador, trazabilidad con la rúbrica).
* `DOCUMENTACION_TAC.md`: especificación del código intermedio.
* `GUIA_GITHUB.md`: publicación en una rama nueva con commits de cada integrante.

## Preguntas probables y dónde está la respuesta

* *¿Cómo decide getReg qué registro derramar?* → `mips_regalloc.py`, método `getreg()`: primero víctimas sin costo (valor muerto o ya en memoria), luego la de siguiente uso más lejano.
* *¿Qué pasa con los temporales en una llamada?* → `save_before_call()`: los `$t` vivos se guardan en el marco; las variables en `$s` no, porque el llamado las preserva.
* *¿Cómo llega una excepción al catch desde otra función?* → `rt_throw` en `mips_runtime.py` restaura `$sp`/`$fp` del registro del manejador; sección 7 de `DOCUMENTACION_MIPS.md`.
* *¿Cómo se sabe que el simulador integrado es correcto?* → `verificar_mips.py --externo` compara cada programa con MARS y SPIM reales.
