# Proyecto 01 — Compiscript

Proyecto para **Construcción de Compiladores 2026, II**. Implementa análisis **léxico, sintáctico y semántico** de Compiscript con **ANTLR**, tabla de símbolos con alcances e **IDE gráfico**.

El programa se limita al análisis: **no ejecuta Compiscript, no genera código intermedio y no genera código objeto**.

## Ejecución

En Windows, PowerShell o CMD, dentro de la carpeta del proyecto:

```powershell
python iniciar.py
```

`iniciar.py` instala, si hace falta, `antlr4-python3-runtime==4.9.3` y abre el IDE.

También puede ejecutarse manualmente:

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Requisitos

- Python 3.10 o superior recomendado.
- Tkinter.
- `antlr4-python3-runtime==4.9.3`.
- Java 8 o superior **solo si se modifica la gramática y hay que regenerar ANTLR**.

## Funcionalidad del IDE

- editor de archivos `.cps`;
- abrir y guardar archivos desde la interfaz;
- análisis completo con **F5**;
- errores léxicos, sintácticos y semánticos dentro del IDE;
- línea, columna, regla/código, explicación y sugerencia;
- recuperación para continuar después de errores;
- pestaña de **Tabla de símbolos**;
- pestaña de **Árbol sintáctico**;
- ventana para cargar la batería de **pruebas semánticas**;
- modo claro/oscuro.

## Archivos de la entrega

```text
Proyecto01_Compiscript_ENTREGA/
├── Compiscript.g4
├── main.py
├── iniciar.py
├── bootstrap.py
├── analyzer.py
├── semantic_analyzer.py
├── symbol_table.py
├── error_listener.py
├── analysis_result.py
├── parse_tree_utils.py
├── verificar_proyecto.py
├── requirements.txt
├── README.md
├── DOCUMENTACION_ARQUITECTURA.md
├── .gitignore
├── generated/
│   ├── __init__.py
│   ├── CompiscriptLexer.py
│   ├── CompiscriptParser.py
│   ├── CompiscriptVisitor.py
│   └── .grammar.sha256
├── pruebas_semanticas/
│   ├── manifest.json
│   └── *.cps
└── pruebas_recuperacion/
    ├── manifest.json
    └── *.cps
```

No se incluyen archivos del laboratorio anterior, cachés de Python ni artefactos auxiliares de ANTLR que no son usados por la aplicación.

## Arquitectura

```text
Código .cps / editor
        │
        ▼
 CompiscriptLexer ──► errores léxicos
        │
        ▼
 CommonTokenStream
        │
        ▼
 CompiscriptParser ──► errores sintácticos + parse tree
        │
        ▼
 SemanticAnalyzer (ANTLR Visitor)
        │
        ├──► sistema de tipos y reglas semánticas
        ├──► SymbolTable + Scope
        └──► clases, funciones y miembros
        │
        ▼
        IDE
 diagnósticos + símbolos + árbol
```

La descripción detallada está en `DOCUMENTACION_ARQUITECTURA.md`.

## Reglas semánticas implementadas

### Sistema de tipos

- operaciones aritméticas y lógicas;
- comparaciones compatibles;
- asignaciones compatibles;
- constantes inicializadas y no reasignables;
- arreglos homogéneos e índices válidos;
- soporte de `integer`, `float`, `string`, `boolean`, clases, arreglos y `null`.

### Ámbitos

- ámbito global y ámbitos anidados;
- resolución de nombres;
- error por identificadores no declarados;
- detección de redeclaración en el mismo ámbito;
- sombreado en ámbitos hijos;
- entornos para funciones, clases y bloques.

### Funciones

- cantidad y tipo de argumentos;
- tipo de retorno;
- recursión;
- funciones anidadas y closures;
- funciones y parámetros duplicados.

### Control de flujo

- condiciones booleanas;
- `break` y `continue` solo dentro de ciclos;
- `return` solo dentro de funciones;
- detección de código muerto.

### Clases y objetos

- atributos y métodos;
- herencia básica;
- constructores;
- `this`;
- validación de miembros accedidos con `.`.

## Tabla de símbolos

`SymbolTable` implementa las operaciones evaluadas en la rúbrica:

```python
insert(symbol)
lookup(name)
update(name, **changes)
enter_scope(name, kind)
exit_scope()
```

## Pruebas

Para ejecutar la batería del proyecto:

```powershell
python verificar_proyecto.py
```

El script ejecuta los casos semánticos definidos en `pruebas_semanticas/manifest.json`, valida los casos de recuperación léxica y sintáctica de `pruebas_recuperacion/manifest.json` y comprueba también:

- recuperación después de múltiples errores léxicos;
- recuperación después de múltiples errores sintácticos;
- recuperación combinada léxica + sintáctica;
- insertar en la tabla de símbolos;
- recuperar información;
- actualizar información;
- manejo de alcances y sombreado.

## ANTLR

Los archivos necesarios para ejecutar el parser ya están en `generated/`. Si se modifica `Compiscript.g4`, `bootstrap.py` regenera el lexer, parser y visitor. Si el `.jar` de ANTLR no existe, el script intenta descargarlo automáticamente.

También puede regenerarse con:

```powershell
python bootstrap.py
```

## Entrega en GitHub

Cada integrante debe realizar sus propios commits para que las contribuciones sean identificables en el historial del repositorio.
