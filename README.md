# Compiscript IDE â€” Proyecto 2: generaciÃ³n de cÃ³digo intermedio (TAC)

Entrega construida sobre **PRY1-Compis-main**. Incluye cÃ³digo fuente, archivos generados de ANTLR, un editor Tkinter, anÃ¡lisis lÃ©xico/sintÃ¡ctico/semÃ¡ntico, tabla de sÃ­mbolos con registros de activaciÃ³n, generador de TAC, reciclaje de temporales, exportaciÃ³n y pruebas de Ã©xito/fallo. **No ejecuta Compiscript ni produce cÃ³digo objeto.**

## Inicio rÃ¡pido

**Windows (PowerShell o CMD):**

```powershell
python iniciar.py
```

**macOS / Linux:**

```bash
python3 iniciar.py
```

`iniciar.py` prepara `antlr4-python3-runtime==4.9.3` si hace falta. Como alternativa, para instalarlo explÃ­citamente:

```bash
python -m pip install -r requirements.txt
python main.py
```

Se requiere **Python 3.10+**, **Tkinter** y la dependencia ANTLR listada en `requirements.txt`. En Ubuntu/Debian, si falta Tkinter: `sudo apt install python3-tk`. Incluimos `generated/` para que **no sea necesario Java durante la ejecuciÃ³n normal**. Java/ANTLR se necesitan Ãºnicamente para regenerar el parser tras editar `Compiscript.g4` (ver `bootstrap.py`).

## CÃ³mo usar el IDE

1. Abre `iniciar.py` o ejecuta `python main.py`. Haz clic en **Abrir archivo .cps** o escribe en el editor.
2. Pulsa **Analizar (F5)**. Los errores aparecen en Â«DiagnÃ³sticosÂ», con detalles, lÃ­nea y sugerencia.
3. Si no existen errores lÃ©xicos, sintÃ¡cticos ni semÃ¡nticos, se abre la pestaÃ±a **CÃ³digo intermedio (TAC)**. Usa **Exportar .tac** para guardar las instrucciones numeradas. **Si hay errores, la pestaÃ±a se limpia y no se produce TAC.**
4. La pestaÃ±a **Tabla de sÃ­mbolos** muestra el almacenamiento, offset y registro de activaciÃ³n; Â«Ãrbol sintÃ¡cticoÂ» presenta el Ã¡rbol de ANTLR.
5. La letra del editor y los resultados es mayor que en el Proyecto 1. Cambia el tamaÃ±o desde **A+ / Aâˆ’** o **Ctrl + / Ctrl âˆ’**. Sobre el editor tambiÃ©n puedes usar **Ctrl + rueda del ratÃ³n**. El modo claro/oscuro se conserva.
6. **Pruebas P1/P2** permite abrir directamente cualquiera de los archivos de prueba.

Se pueden usar `Ctrl+O` para abrir, `Ctrl+S` para guardar, `Ctrl+MayÃºs+S` para Guardar como y `Ctrl+T` para alternar los temas.

## Ejecutar todas las pruebas

```bash
python verificar_proyecto.py
```

Se verifican **57** casos semanticos, **3** de recuperacion, **4** operaciones basicas de tabla de simbolos, **30** casos de TAC y **4** invariantes de TAC/almacenamiento, mas **40** regresiones estructurales: **138 verificaciones automatizadas** en total. Las pruebas negativas tambien verifican que no se genera ninguna representacion intermedia. Los casos estan en `pruebas_semanticas/`, `pruebas_recuperacion/`, `pruebas_tac/` y `pruebas_regresion/`. La interfaz real se verifica aparte con `python verificar_interfaz.py` (11 controles; en Linux sin pantalla puedes usar `xvfb-run -a python verificar_interfaz.py`).

Para compilar un archivo desde consola **sin ejecutarlo** (funciÃ³n adicional; no sustituye al IDE):

```bash
python compilar_cli.py pruebas_tac/16_recursion.cps --salida factorial.tac
```

Si existe algÃºn error, muestra diagnÃ³sticos, sale con cÃ³digo distinto de cero y **no crea el archivo de salida**.

## Archivos importantes

| Archivo | Responsabilidad |
| --- | --- |
| `Compiscript.g4`, `generated/` | GramÃ¡tica y lexer/parser/Visitor generados por ANTLR |
| `error_listener.py` | DiagnÃ³sticos y recuperaciÃ³n con mensajes en espaÃ±ol |
| `semantic_analyzer.py` | Reglas semÃ¡nticas, Ã¡mbitos y vÃ­nculo de nodos con sus Ã¡mbitos |
| `symbol_table.py` | SÃ­mbolos, almacenamiento relativo, layout de campos y frames |
| `tac_ir.py` | Instrucciones TAC estructuradas y administrador de temporales |
| `tac_generator.py` | Visitor que transforma el Ã¡rbol de ANTLR en TAC |
| `analyzer.py` | Pipeline que **bloquea** el TAC si hay errores |
| `main.py` | IDE con editor, pestaÃ±as, zoom y exportaciÃ³n |
| `verificar_proyecto.py` / `verificar_regresiones.py` | Suite automatizada de 138 verificaciones (incluye 40 regresiones estructurales) |
| `DOCUMENTACION_TAC.md` | DiseÃ±o detallado, convenciÃ³n de instrucciones y supuestos |
| `DOCUMENTACION_ARQUITECTURA.md` | Arquitectura, etapas y decisiones de diseÃ±o |

## Alcance y diferencias con el Proyecto 1

- Se conserva ANTLR 4.9.3 y el proyecto anterior; se aÃ±ade generaciÃ³n de cÃ³digo intermedio y almacenamiento abstracto, **no** un intÃ©rprete ni un backend.
- El modo predeterminado usa la gramática oficial de Compiscript: tipos primitivos `integer`, `boolean` y `string`; no se acepta `float` como extensión.
- `const` requiere inicializador en la gramática (`const id ... = expresión;`); si falta, se reporta como error sintáctico y no se produce TAC.
- Se corrigiÃ³ el anÃ¡lisis de `switch` para admitir discriminantes escalares, como `integer`, segÃºn el ejemplo del README pÃºblico, y permitir `break` dentro de `switch`. La prueba negativa antigua `30_condicion_switch_error.cps` ahora utiliza un arreglo, que sÃ­ debe ser rechazado.
- La documentacion historica del Proyecto 1 se conserva para consulta en `DOCUMENTACION_ARQUITECTURA_PROYECTO1.md`; el README vigente es este.

## Correcciones verificadas respecto de la versiÃ³n anterior

- `for` con condiciÃ³n ausente: el semÃ¡ntico y el Visitor TAC separan la condiciÃ³n y el incremento por la posiciÃ³n real de los puntos y coma, no por la longitud de `ctx.expression()`.
- `return`, `break` y `continue` dentro de `try`: la traducciÃ³n retira solo los manejadores cuyo alcance realmente termina; no retira el del `try` externo cuando el salto permanece dentro de Ã©l.
- EvaluaciÃ³n con efectos laterales: una variable o referencia evaluada antes de una operaciÃ³n/llamada/Ã­ndice se copia a un temporal antes de evaluar operandos posteriores que podrÃ­an modificarla.
- Se evalÃºan los argumentos de `new Clase(...)` antes de los inicializadores de campos y de la invocaciÃ³n al constructor, para respetar los efectos laterales.
- El IDE invalida el TAC anterior al editar el cÃ³digo, al iniciar una nueva compilaciÃ³n o ante un fallo inesperado del compilador; **no puede exportarse TAC obsoleto**.
- `pruebas_regresion/` incluye 11 `.cps` adicionales que se pueden abrir desde "Abrir archivo .cps" y `verificar_regresiones.py` comprueba invariantes estructurales del TAC y del analisis.

**Alcance de la verificaciÃ³n:** pruebas estÃ¡ticas y del IDE en Linux bajo pantalla virtual. No se ejecutan programas Compiscript (prohibido por el proyecto). La rÃºbrica y pruebas privadas de la cÃ¡tedra, el funcionamiento en cada Windows/macOS y el historial real de GitHub no pueden certificarse desde esta entrega.

## Entrega

Los requisitos oficiales piden entregar un **repositorio GitHub y commits verificables de cada integrante**. Este ZIP incluye la base tÃ©cnica y la documentaciÃ³n; cada integrante debe revisar, acreditar y subir sus propias contribuciones reales. No se incluyen commits fabricados ni se ha publicado el repositorio automÃ¡ticamente.
