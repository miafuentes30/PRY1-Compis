# Compiscript IDE — Proyecto 3: generación de código MIPS

Compilador completo de **Compiscript** construido sobre los Proyectos 1 y 2 (mismo repositorio, rama nueva): análisis léxico, sintáctico y semántico con ANTLR, código intermedio de tres direcciones (TAC) y, en esta fase, **generación de ensamblador MIPS** con registros de activación, asignación de registros (`getReg`), optimización por mirilla y ejecución en un simulador. El ensamblador generado corre sin cambios en **MARS 4.5** (incluido), **SPIM** y **QtSpim**.

## Inicio rápido

Requisitos: **Python 3.10+** con Tkinter. Java 8+ solo si quieres usar MARS.

**Windows:** doble clic en `iniciar_windows.bat` o:

```powershell
python iniciar.py
```

**macOS / Linux:**

```bash
python3 iniciar.py          # o ./iniciar_linux_mac.sh
```

`iniciar.py` instala `antlr4-python3-runtime==4.9.3` si hace falta y abre el IDE. También puedes hacerlo manualmente:

```bash
python -m pip install -r requirements.txt
python main.py
```

En Ubuntu/Debian, si falta Tkinter: `sudo apt install python3-tk`. Los archivos de ANTLR ya generados están en `generated/`, por lo que no se necesita Java para compilar.

## Cómo usar el IDE

1. Abre un `.cps` (**Abrir archivo .cps** o `Ctrl+O`), escribe en el editor o pulsa **Pruebas** y elige uno de los programas de prueba.
2. **Compilar (F5)**: ejecuta todas las fases. Si hay errores aparecen en **Diagnósticos** (con línea, columna y sugerencia) y no se genera TAC ni MIPS.
3. Si compila, la pestaña **MIPS** muestra el ensamblador. **Exportar .asm** lo guarda para abrirlo en MARS o QtSpim; **Abrir MARS** abre el simulador incluido.
4. **Ejecutar (F6)**: corre el programa en el simulador integrado. La pestaña **Ejecución** muestra la salida, el código de salida y estadísticas; **Comparar MARS/SPIM** ejecuta el mismo `.asm` en los simuladores reales y confirma que la salida es idéntica.
5. **Activación**: árbol de activación de la última ejecución (cada llamada con sus argumentos y su valor de retorno).
6. **Registros**: estadísticas de `getReg()` (derrames, reutilizaciones, guardados antes de llamadas), registros `$s` asignados y el registro de activación de cada función.
7. **Mirilla**: transformaciones aplicadas, con el código antes y después. La casilla **Optimización por mirilla** permite compilar sin optimizar para comparar.
8. **TAC**, **Símbolos** y **Árbol ANTLR** conservan las vistas de los proyectos anteriores.

Atajos: `F5` compilar, `F6` ejecutar, `Ctrl+S` guardar, `Ctrl+T` modo oscuro, `Ctrl +/-` tamaño de letra.

## Compilar desde la consola

```bash
python compilar_cli.py pruebas_mips/13_recursion.cps --asm recursion.asm        # genera MIPS
python compilar_cli.py pruebas_mips/19_arbol_activacion.cps --ejecutar --arbol  # ejecuta y muestra el árbol
python compilar_cli.py pruebas_mips/16_herencia.cps --ejecutar --mars --spim    # compara con MARS y SPIM
python compilar_cli.py pruebas_mips/18_presion_registros.cps --reporte          # getReg, marcos y mirilla
python compilar_cli.py programa.cps --salida programa.tac                        # solo TAC (Proyecto 2)
```

`--sin-optimizar` desactiva la mirilla. Con errores, se muestran los diagnósticos, el código de salida es distinto de cero y no se crea ningún archivo.

## Ejecutar el `.asm` en un simulador MIPS

* **MARS 4.5** (incluido): `java -jar herramientas/Mars4_5.jar nc programa.asm` en consola, o `java -jar herramientas/Mars4_5.jar` para la interfaz: *File → Open*, *Run → Assemble* (F3), *Run → Go* (F5).
* **SPIM**: `spim -file programa.asm`.
* **QtSpim**: *File → Reinitialize and Load File*, luego *Run* (F5).

## Pruebas

```bash
python verificar_proyecto.py             # 197 verificaciones (P1 + P2 + P3)
python verificar_mips.py                 # solo P3: 26 programas + 29 pruebas unitarias
python verificar_mips.py --externo       # además compara cada programa con MARS y SPIM
python verificar_interfaz.py             # 19 comprobaciones del IDE (Linux sin pantalla: xvfb-run -a ...)
```

En Windows, `verificar_windows.bat` ejecuta la batería completa.

`pruebas_mips/` contiene casos exitosos y fallidos para cada punto de la rúbrica (variables, aritmética, lógica, arreglos, control de flujo, funciones, recursión, clases, herencia, try/catch, presión de registros, árbol de activación, errores en tiempo de ejecución y de compilación) con su salida esperada en `manifest.json`. Se conservan `pruebas_semanticas/`, `pruebas_recuperacion/`, `pruebas_tac/` y `pruebas_regresion/` de las fases anteriores.

## Archivos principales

| Archivo | Responsabilidad |
| --- | --- |
| `main.py` | IDE (editor, diagnósticos, TAC, MIPS, ejecución, activación, registros, mirilla) |
| `compilar_cli.py` | Compilador de consola |
| `analyzer.py` | Pipeline completo: léxico → sintáctico → semántico → TAC → MIPS |
| `semantic_analyzer.py`, `symbol_table.py` | Análisis semántico y tabla de símbolos |
| `tac_ir.py`, `tac_generator.py` | Código intermedio |
| `mips_analysis.py` | Bloques básicos, flujo de control y variables vivas |
| `mips_frames.py` | Registros de activación, enlaces de acceso, objetos y vtables |
| `mips_regalloc.py` | `getReg()` y descriptores de registros |
| `mips_codegen.py` | Traducción TAC → MIPS, secuencias de llamada y retorno |
| `mips_runtime.py` | Biblioteca de tiempo de ejecución en MIPS |
| `mips_peephole.py` | Optimización por mirilla |
| `mips_simulator.py`, `mips_external.py` | Simulador integrado; MARS y SPIM |
| `herramientas/Mars4_5.jar` | Simulador MARS 4.5 (licencia MIT) |
| `DOCUMENTACION_ARQUITECTURA.md` | Arquitectura del compilador |
| `DOCUMENTACION_MIPS.md` | Diseño del backend MIPS |
| `DOCUMENTACION_TAC.md` | Especificación del TAC |
| `ENTREGA_Y_DEMOSTRACION.md` | Guion de demostración |
| `GUIA_GITHUB.md` | Cómo subir esta fase en una rama nueva con commits de cada integrante |

## Cambios respecto del Proyecto 2

* Nuevo backend MIPS completo, simulador integrado, MARS incluido, pestañas y botones nuevos en el IDE y opciones nuevas en la consola.
* `string + integer` y `string + boolean` concatenan (lo usa el programa de ejemplo oficial); una instancia derivada se acepta donde se espera la clase base (polimorfismo). Ambas reglas tienen pruebas positivas y negativas.
* El TAC conserva los tipos estáticos de cada instrucción; su forma textual no cambió.
* Los miembros de clase usados sin `this.` dentro de un método ahora se traducen correctamente.
* Se corrigió la codificación de los documentos de la fase anterior.
