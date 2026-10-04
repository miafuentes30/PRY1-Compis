# Documentación de arquitectura — Proyecto 01 Compiscript

## 1. Objetivo

El sistema analiza código Compiscript sin ejecutarlo. El flujo combina ANTLR para las fases léxica y sintáctica con un Visitor para el análisis semántico.

## 2. Flujo del análisis

1. `main.py` permite escribir o abrir un archivo `.cps`.
2. `analyzer.py` crea un `InputStream`.
3. `CompiscriptLexer` tokeniza la entrada y `SpanishErrorListener` recopila errores léxicos.
4. `CommonTokenStream.fill()` fuerza el recorrido completo del lexer.
5. `CompiscriptParser` construye el árbol usando recuperación de errores de ANTLR.
6. Si no hay errores léxicos/sintácticos, `SemanticAnalyzer` recorre el árbol con `CompiscriptVisitor`.
7. El visitor consulta y modifica `SymbolTable` y la información de clases.
8. `FullAnalysisResult` devuelve diagnósticos, árbol y tabla de símbolos al IDE.
9. El IDE muestra los resultados en sus pestañas.

## 3. Generación con ANTLR

La gramática se encuentra en `Compiscript.g4`.

`bootstrap.py` compara el SHA-256 de la gramática con `generated/.grammar.sha256`. Si cambia, genera:

- `CompiscriptLexer.py`;
- `CompiscriptParser.py`;
- `CompiscriptVisitor.py`.

La generación usa ANTLR y no una implementación manual del lexer o parser.

## 4. Diagnósticos

`AnalysisError` contiene:

- tipo de error: léxico, sintáctico o semántico;
- línea y columna;
- símbolo asociado;
- descripción;
- sugerencia;
- fragmento de código;
- código estable de error para las pruebas.

## 5. Sistema de tipos

Se manejan, entre otros:

- `integer`;
- `float`;
- `string`;
- `boolean`;
- `null`;
- arreglos `T[]`;
- clases;
- `function`;
- `void`;
- `unknown` como tipo de recuperación.

`unknown` evita generar cascadas de errores cuando una expresión ya contiene un problema previo.

## 6. Tabla de símbolos y alcances

### Symbol

Un símbolo almacena nombre, clase de símbolo, tipo, mutabilidad, inicialización, posición, alcance, firma y clase propietaria cuando corresponde.

### Scope

Cada alcance mantiene:

- identificador;
- nombre;
- tipo de entorno;
- alcance padre;
- profundidad;
- símbolos locales.

### Resolución

`lookup()` comienza en el alcance actual y asciende por los padres. Esto permite ámbitos anidados, sombreado y closures.

Las operaciones principales son:

- `insert()`;
- `lookup()`;
- `update()`;
- `enter_scope()`;
- `exit_scope()`.

## 7. Funciones

El analizador valida:

- declaraciones duplicadas;
- parámetros duplicados;
- cantidad y tipo de argumentos;
- retorno;
- recursión;
- funciones anidadas y closures.

Las funciones se predeclaran dentro de su ámbito para permitir recursión y llamadas válidas antes de analizar su cuerpo.

## 8. Clases

`ClassInfo` conserva nombre, clase padre, atributos y métodos. La búsqueda de miembros puede recorrer la cadena de herencia.

El análisis valida acceso a miembros, constructores y uso de `this`.

## 9. Recuperación de errores

- **Lexer:** procesa toda la entrada incluso ante caracteres inválidos.
- **Parser:** usa la estrategia de recuperación estándar de ANTLR.
- **Semántica:** registra un error y continúa el recorrido siempre que sea posible.
- Se deduplican diagnósticos para evitar repeticiones poco útiles.
- Si la fase léxica o sintáctica falla, no se ejecuta la fase semántica sobre un árbol dañado, evitando cascadas artificiales.

## 10. Árbol sintáctico

El parse tree generado por ANTLR se convierte a etiquetas legibles mediante `parse_tree_utils.py` y se muestra en un `ttk.Treeview` dentro del IDE.

## 11. Pruebas

`pruebas_semanticas/manifest.json` define el resultado esperado para cada archivo `.cps` de reglas semánticas.

`pruebas_recuperacion/manifest.json` contiene casos dedicados a comprobar que el lexer y el parser continúan después de varios errores en una misma ejecución.

`verificar_proyecto.py` ejecuta ambas baterías y comprueba además las cuatro operaciones de tabla de símbolos evaluadas en la rúbrica: insertar, recuperar, actualizar y manejar alcances.
