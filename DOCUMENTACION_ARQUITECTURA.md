# Arquitectura del compilador — Proyecto 2

## 1. Objetivo

Traducir programas Compiscript a un código intermedio de tres direcciones **sin ejecutarlos**. El usuario escribe o abre un archivo `.cps` en la interfaz Tkinter, analiza y ve dentro de la misma interfaz diagnósticos, árbol, símbolos y TAC.

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
        Si hay errores léxicos/sintácticos -> diagnósticos; TAC = None
            |
        SemanticAnalyzer (ANTLR Visitor)
            |          |               |
         tipos       ámbitos      clases/herencia
            |          |               |
        Si hay errores semánticos -> diagnósticos; TAC = None
            |
        SymbolTable.plan_storage(classes)
            |
        TACGenerator (segundo ANTLR Visitor)
            |                 |
       TACProgram        TemporaryPool por función
            |
        pestaña TAC / exportación .tac
```

El análisis léxico utiliza `tokens.fill()` para llegar al EOF y recopilar errores. El parser emplea la recuperación integrada de ANTLR (inserción/eliminación de tokens). Se deduplican los diagnósticos por tipo, posición, regla y descripción; el Visitor semántico visita las otras sentencias incluso tras un error recuperable. No se ejecuta el Visitor semántico sobre un árbol con errores léxicos/sintácticos para evitar cascadas falsas.

## 3. Clases y responsabilidades

- `CompiscriptAnalyzer`: orquesta etapas, detiene la generación de TAC ante cualquier error, devuelve `FullAnalysisResult` con árbol, símbolos, diagnósticos y un `TACProgram | None`.
- `SemanticAnalyzer`: comprueba tipos, declaraciones, ámbitos, constantes, condiciones, llamadas, retornos, clases, métodos, herencia, acceso a propiedades, índices y excepciones. A cada nodo que abre ámbito (bloque, función, clase, for, foreach, switch, catch) se le anota el ID de su ámbito semántico. Esto permite al Visitor TAC recuperar nombres y offsets correctos con sombreado.
- `SymbolTable`: ámbitos numerados, símbolos en ámbitos anidados, `lookup`, `insert`, `update`, `plan_storage` y `rows`. `plan_storage` asigna un **frame por función/método**, slots de parámetro positivos y locales negativos; los campos reciben offsets heredados.
- `TACGenerator`: segundo ANTLR Visitor independiente. Genera instrucciones estructuradas y nombres `variable@sÁMBITO`, administra etiquetas únicas, pilas de destinos de `break`/`continue` con profundidad de manejadores `try` activos, colas de funciones/métodos y secciones de inicialización de campos. Compila el programa principal y después las definiciones de funciones, que no se ejecutan durante el análisis.
- `TemporaryPool`: temporales activos/libres por función, liberación tras el último uso, reutilización de registros liberados y sobrescritura en sitio cuando la operación lo permite. Reporta el máximo de temporales simultáneos, las reservas y las reutilizaciones.
- `TACProgram` / `Instruction`: representación en memoria por opcode/argumentos/línea de origen, renderizado legible y con números de línea.
- `CompiscriptApp`: interfaz Tkinter de pestañas, editor con resaltado y números de línea, zoom, búsqueda de archivos `.cps`, exportación de `.tac`, tablas y diagnósticos.

## 4. Registros de activación

Se usa un **modelo abstracto**, no direcciones de memoria reales. Un slot ocupa 8 bytes. Cada llamada de función crea su propio frame, por lo que llamadas recursivas no comparten las instancias de sus parámetros y variables locales.

```text
  parámetros (param 0)      FP + 16
  parámetros (param 1)      FP + 24
  dirección de retorno      FP +  8  (convención conceptual)
  puntero a frame previo    FP +  0  (convención conceptual)
  variable local 0          FP -  8
  variable local 1          FP - 16
  temporales t0...          banco propio del frame
```

Los bloques anidados de una función usan el mismo frame, pero sus nombres llevan sufijo `@sID` para evitar colisiones por sombreado. Cada función utiliza su propio banco de temporales. La tabla de símbolos registra `storage_class`, `offset`, `size`, `frame_name` y `tac_name`; la pestaña los muestra. Los objetos contienen los campos heredados antes que los nuevos. Clases, funciones y métodos aparecen como símbolos de tipo/segmento de código, no como variables locales.

## 5. Decisiones de integración y manejo de errores

- Primero se valida el programa; **no hay TAC parcial**. Si falla cualquier fase, el resultado incluye diagnósticos y `tac=None`.
- El IDE elimina el TAC anterior tras una nueva compilación fallida y también cuando se modifica el texto fuente.
- El error `TAC_UNSUPPORTED` solo se emite cuando un programa semánticamente válido usa una construcción que el traductor no pudo convertir. En tal caso se rechaza el resultado completo y no se muestra TAC engañoso.
- La gramática no se ha sustituido por un parser manual; se entregan los archivos de ANTLR generados y los fuentes `.g4`.
- Se mantiene `float` y la validación semántica de constantes sin inicializador por compatibilidad con la suite del Proyecto 1.
- No se optimiza ni se ejecuta el TAC, no se realizan operaciones reales sobre memoria, no se emite ensamblador ni código objeto.

## 6. Comprobación de calidad

Ejecutar `python verificar_proyecto.py`. Se entregan 57 pruebas semánticas, 3 de recuperación, 4 de tabla, 30 de TAC, 4 invariantes y 25 nuevas regresiones: 123 verificaciones automáticas. Además, `verificar_interfaz.py` ejecuta 11 verificaciones del IDE real, incluidas apertura de archivos, exportación, bloqueo del TAC obsoleto, ampliación de letra y temas, usando una pantalla virtual (`xvfb`) en Linux; el aspecto exacto puede variar según el sistema operativo y la disponibilidad de fuentes.

Consultar `DOCUMENTACION_TAC.md` para la especificación de instrucciones y ejemplos.
