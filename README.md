# Compiscript IDE — Proyecto 2: generación de código intermedio (TAC)

Entrega construida sobre **PRY1-Compis-main**. Incluye código fuente, archivos generados de ANTLR, un editor Tkinter, análisis léxico/sintáctico/semántico, tabla de símbolos con registros de activación, generador de TAC, reciclaje de temporales, exportación y pruebas de éxito/fallo. **No ejecuta Compiscript ni produce código objeto.**

## Inicio rápido

**Windows (PowerShell o CMD):**

```powershell
python iniciar.py
```

**macOS / Linux:**

```bash
python3 iniciar.py
```

`iniciar.py` prepara `antlr4-python3-runtime==4.9.3` si hace falta. Como alternativa, para instalarlo explícitamente:

```bash
python -m pip install -r requirements.txt
python main.py
```

Se requiere **Python 3.10+**, **Tkinter** y la dependencia ANTLR listada en `requirements.txt`. En Ubuntu/Debian, si falta Tkinter: `sudo apt install python3-tk`. Incluimos `generated/` para que **no sea necesario Java durante la ejecución normal**. Java/ANTLR se necesitan únicamente para regenerar el parser tras editar `Compiscript.g4` (ver `bootstrap.py`).

## Cómo usar el IDE

1. Abre `iniciar.py` o ejecuta `python main.py`. Haz clic en **Abrir archivo .cps** o escribe en el editor.
2. Pulsa **Analizar (F5)**. Los errores aparecen en «Diagnósticos», con detalles, línea y sugerencia.
3. Si no existen errores léxicos, sintácticos ni semánticos, se abre la pestaña **Código intermedio (TAC)**. Usa **Exportar .tac** para guardar las instrucciones numeradas. **Si hay errores, la pestaña se limpia y no se produce TAC.**
4. La pestaña **Tabla de símbolos** muestra el almacenamiento, offset y registro de activación; «Árbol sintáctico» presenta el árbol de ANTLR.
5. La letra del editor y los resultados es mayor que en el Proyecto 1. Cambia el tamaño desde **A+ / A−** o **Ctrl + / Ctrl −**. Sobre el editor también puedes usar **Ctrl + rueda del ratón**. El modo claro/oscuro se conserva.
6. **Pruebas P1/P2** permite abrir directamente cualquiera de los archivos de prueba.

Se pueden usar `Ctrl+O` para abrir, `Ctrl+S` para guardar, `Ctrl+Mayús+S` para Guardar como y `Ctrl+T` para alternar los temas.

## Ejecutar todas las pruebas

```bash
python verificar_proyecto.py
```

Se verifican **57** casos semánticos, **3** de recuperación, **4** operaciones básicas de tabla de símbolos, **30** casos nuevos de TAC y **4** invariantes de TAC/almacenamiento: **123 verificaciones automatizadas** en total: las 98 anteriores y **25 regresiones estructurales** nuevas. Las pruebas negativas también verifican que no se genera ninguna representación intermedia. Los casos están en `pruebas_semanticas/`, `pruebas_recuperacion/` y `pruebas_tac/` con manifiestos JSON. El informe de ejecución incluido se encuentra en `REPORTE_PRUEBAS.txt`. La interfaz real se verifica aparte con `python verificar_interfaz.py` (11 controles; en Linux sin pantalla puedes usar `xvfb-run -a python verificar_interfaz.py`).

Para compilar un archivo desde consola **sin ejecutarlo** (función adicional; no sustituye al IDE):

```bash
python compilar_cli.py pruebas_tac/16_recursion.cps --salida factorial.tac
```

Si existe algún error, muestra diagnósticos, sale con código distinto de cero y **no crea el archivo de salida**.

## Archivos importantes

| Archivo | Responsabilidad |
| --- | --- |
| `Compiscript.g4`, `generated/` | Gramática y lexer/parser/Visitor generados por ANTLR |
| `error_listener.py` | Diagnósticos y recuperación con mensajes en español |
| `semantic_analyzer.py` | Reglas semánticas, ámbitos y vínculo de nodos con sus ámbitos |
| `symbol_table.py` | Símbolos, almacenamiento relativo, layout de campos y frames |
| `tac_ir.py` | Instrucciones TAC estructuradas y administrador de temporales |
| `tac_generator.py` | Visitor que transforma el árbol de ANTLR en TAC |
| `analyzer.py` | Pipeline que **bloquea** el TAC si hay errores |
| `main.py` | IDE con editor, pestañas, zoom y exportación |
| `verificar_proyecto.py` / `verificar_regresiones.py` | Suite automatizada de 123 verificaciones (incluye 25 regresiones) |
| `DOCUMENTACION_TAC.md` | Diseño detallado, convención de instrucciones y supuestos |
| `DOCUMENTACION_ARQUITECTURA.md` | Arquitectura, etapas y decisiones de diseño |

## Alcance y diferencias con el Proyecto 1

- Se conserva ANTLR 4.9.3 y el proyecto anterior; se añade generación de código intermedio y almacenamiento abstracto, **no** un intérprete ni un backend.
- Se mantiene `float` como **extensión heredada del Proyecto 1**, aunque la gramática pública de referencia de Compiscript solo menciona `integer`, `boolean` y `string`.
- Se admite temporalmente `const` sin inicializador en el parser para producir un error **semántico** legible, en lugar de fallar inmediatamente en sintaxis; un programa con dicha declaración jamás produce TAC.
- Se corrigió el análisis de `switch` para admitir discriminantes escalares, como `integer`, según el ejemplo del README público, y permitir `break` dentro de `switch`. La prueba negativa antigua `30_condicion_switch_error.cps` ahora utiliza un arreglo, que sí debe ser rechazado.
- Los archivos del Proyecto 1 se conservan para consulta como `README_PROYECTO1_ORIGINAL.md` y `DOCUMENTACION_ARQUITECTURA_PROYECTO1.md`; el README vigente es este.

## Correcciones verificadas respecto de la versión anterior

- `for` con condición ausente: el semántico y el Visitor TAC separan la condición y el incremento por la posición real de los puntos y coma, no por la longitud de `ctx.expression()`.
- `return`, `break` y `continue` dentro de `try`: la traducción retira solo los manejadores cuyo alcance realmente termina; no retira el del `try` externo cuando el salto permanece dentro de él.
- Evaluación con efectos laterales: una variable o referencia evaluada antes de una operación/llamada/índice se copia a un temporal antes de evaluar operandos posteriores que podrían modificarla.
- Se evalúan los argumentos de `new Clase(...)` antes de los inicializadores de campos y de la invocación al constructor, para respetar los efectos laterales.
- El IDE invalida el TAC anterior al editar el código, al iniciar una nueva compilación o ante un fallo inesperado del compilador; **no puede exportarse TAC obsoleto**.
- `pruebas_regresion/` incluye 11 `.cps` adicionales que se pueden abrir desde «Abrir archivo .cps» y `verificar_regresiones.py` comprueba la semántica estructural de los tres cambios.

**Alcance de la verificación:** pruebas estáticas y del IDE en Linux bajo pantalla virtual. No se ejecutan programas Compiscript (prohibido por el proyecto). La rúbrica y pruebas privadas de la cátedra, el funcionamiento en cada Windows/macOS y el historial real de GitHub no pueden certificarse desde esta entrega.

## Entrega

Los requisitos oficiales piden entregar un **repositorio GitHub y commits verificables de cada integrante**. Este ZIP incluye la base técnica y la documentación; cada integrante debe revisar, acreditar y subir sus propias contribuciones reales. No se incluyen commits fabricados ni se ha publicado el repositorio automáticamente.
