# Arquitectura del compilador â€” Proyecto 2

## 1. Objetivo

Traducir programas Compiscript a un cÃ³digo intermedio de tres direcciones **sin ejecutarlos**. El usuario escribe o abre un archivo `.cps` en la interfaz Tkinter, analiza y ve dentro de la misma interfaz diagnÃ³sticos, Ã¡rbol, sÃ­mbolos y TAC.

## 2. Pipeline

```text
Editor Tkinter / archivo .cps
            |
         ANTLR Lexer + SpanishErrorListener
            |
         CommonTokenStream + ANTLR Parser
            |                    |
            |            RecoveringErrorStrategy
            |                    |
        Si hay errores lÃ©xicos/sintÃ¡cticos -> diagnÃ³sticos; TAC = None
            |
        SemanticAnalyzer (ANTLR Visitor)
            |          |               |
         tipos       Ã¡mbitos      clases/herencia
            |          |               |
        Si hay errores semÃ¡nticos -> diagnÃ³sticos; TAC = None
            |
        SymbolTable.plan_storage(classes)
            |
        TACGenerator (segundo ANTLR Visitor)
            |                 |
       TACProgram        TemporaryPool por funciÃ³n
            |
        pestaÃ±a TAC / exportaciÃ³n .tac
```

El anÃ¡lisis lÃ©xico utiliza `tokens.fill()` para llegar al EOF y recopilar errores. El parser emplea la recuperaciÃ³n integrada de ANTLR (inserciÃ³n/eliminaciÃ³n de tokens). Se deduplican los diagnÃ³sticos por tipo, posiciÃ³n, regla y descripciÃ³n; el Visitor semÃ¡ntico visita las otras sentencias incluso tras un error recuperable. No se ejecuta el Visitor semÃ¡ntico sobre un Ã¡rbol con errores lÃ©xicos/sintÃ¡cticos para evitar cascadas falsas.

## 3. Clases y responsabilidades

- `CompiscriptAnalyzer`: orquesta etapas, detiene la generaciÃ³n de TAC ante cualquier error, devuelve `FullAnalysisResult` con Ã¡rbol, sÃ­mbolos, diagnÃ³sticos y un `TACProgram | None`.
- `SemanticAnalyzer`: comprueba tipos, declaraciones, Ã¡mbitos, constantes, condiciones, llamadas, retornos, clases, mÃ©todos, herencia, acceso a propiedades, Ã­ndices y excepciones. A cada nodo que abre Ã¡mbito (bloque, funciÃ³n, clase, for, foreach, switch, catch) se le anota el ID de su Ã¡mbito semÃ¡ntico. Esto permite al Visitor TAC recuperar nombres y offsets correctos con sombreado.
- `SymbolTable`: Ã¡mbitos numerados, sÃ­mbolos en Ã¡mbitos anidados, `lookup`, `insert`, `update`, `plan_storage` y `rows`. `plan_storage` asigna un **frame por funciÃ³n/mÃ©todo**, slots de parÃ¡metro positivos y locales negativos; los campos reciben offsets heredados.
- `TACGenerator`: segundo ANTLR Visitor independiente. Genera instrucciones estructuradas y nombres `variable@sÃMBITO`, administra etiquetas Ãºnicas, pilas de destinos de `break`/`continue` con profundidad de manejadores `try` activos, colas de funciones/mÃ©todos y secciones de inicializaciÃ³n de campos. Compila el programa principal y despuÃ©s las definiciones de funciones, que no se ejecutan durante el anÃ¡lisis.
- `TemporaryPool`: temporales activos/libres por funciÃ³n, liberaciÃ³n tras el Ãºltimo uso, reutilizaciÃ³n de registros liberados y sobrescritura en sitio cuando la operaciÃ³n lo permite. Reporta el mÃ¡ximo de temporales simultÃ¡neos, las reservas y las reutilizaciones.
- `TACProgram` / `Instruction`: representaciÃ³n en memoria por opcode/argumentos/lÃ­nea de origen, renderizado legible y con nÃºmeros de lÃ­nea.
- `CompiscriptApp`: interfaz Tkinter de pestaÃ±as, editor con resaltado y nÃºmeros de lÃ­nea, zoom, bÃºsqueda de archivos `.cps`, exportaciÃ³n de `.tac`, tablas y diagnÃ³sticos.

## 4. Registros de activaciÃ³n

Se usa un **modelo abstracto**, no direcciones de memoria reales. Un slot ocupa 8 bytes. Cada llamada de funciÃ³n crea su propio frame, por lo que llamadas recursivas no comparten las instancias de sus parÃ¡metros y variables locales.

```text
  parÃ¡metros (param 0)      FP + 16
  parÃ¡metros (param 1)      FP + 24
  direcciÃ³n de retorno      FP +  8  (convenciÃ³n conceptual)
  puntero a frame previo    FP +  0  (convenciÃ³n conceptual)
  variable local 0          FP -  8
  variable local 1          FP - 16
  temporales t0...          banco propio del frame
```

Los bloques anidados de una funciÃ³n usan el mismo frame, pero sus nombres llevan sufijo `@sID` para evitar colisiones por sombreado. Cada funciÃ³n utiliza su propio banco de temporales. La tabla de sÃ­mbolos registra `storage_class`, `offset`, `size`, `frame_name` y `tac_name`; la pestaÃ±a los muestra. Los objetos contienen los campos heredados antes que los nuevos. Clases, funciones y mÃ©todos aparecen como sÃ­mbolos de tipo/segmento de cÃ³digo, no como variables locales.

## 5. Decisiones de integraciÃ³n y manejo de errores

- Primero se valida el programa; **no hay TAC parcial**. Si falla cualquier fase, el resultado incluye diagnÃ³sticos y `tac=None`.
- El IDE elimina el TAC anterior tras una nueva compilaciÃ³n fallida y tambiÃ©n cuando se modifica el texto fuente.
- El error `TAC_UNSUPPORTED` solo se emite cuando un programa semÃ¡nticamente vÃ¡lido usa una construcciÃ³n que el traductor no pudo convertir. En tal caso se rechaza el resultado completo y no se muestra TAC engaÃ±oso.
- La gramÃ¡tica no se ha sustituido por un parser manual; se entregan los archivos de ANTLR generados y los fuentes `.g4`.
- El modo estándar sigue la gramática oficial: no hay `float` nativo y `const` exige inicializador sintáctico. Cualquier extensión histórica queda fuera del comportamiento predeterminado.
- No se optimiza ni se ejecuta el TAC, no se realizan operaciones reales sobre memoria, no se emite ensamblador ni cÃ³digo objeto.

## 6. ComprobaciÃ³n de calidad

Ejecutar `python verificar_proyecto.py`. Se entregan 57 pruebas semanticas, 3 de recuperacion, 4 de tabla, 30 de TAC, 4 invariantes y 40 regresiones estructurales: 138 verificaciones automaticas. Ademas, `verificar_interfaz.py` ejecuta 11 verificaciones del IDE real, incluidas apertura de archivos, exportacion, bloqueo del TAC obsoleto, ampliacion de letra y temas, usando una pantalla virtual (`xvfb`) en Linux; el aspecto exacto puede variar segun el sistema operativo y la disponibilidad de fuentes.

Consultar `DOCUMENTACION_TAC.md` para la especificaciÃ³n de instrucciones y ejemplos.
