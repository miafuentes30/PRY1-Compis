# Especificación del código intermedio (TAC)

**Ámbito:** traducción estática de Compiscript a un IR de tres direcciones, sin ejecución ni generación de código objeto. Su sintaxis es una decisión del grupo, permitida por la especificación oficial. Cada `Instruction` conserva opcode, argumentos y línea de origen cuando se dispone de ella; la vista del IDE muestra instrucciones numeradas y la exportación conserva la misma numeración.

## Convenciones

- Variables: `nombre@sID`, donde `ID` identifica el ámbito semántico y evita colisiones por sombreado. Ej.: `x@s0`, `x@s2`.
- Temporales: `t0`, `t1`... propios de cada función o del `main`. Se pueden volver a utilizar tras su último uso o sobrescribir en una operación `t0 = t0 + ...`. Se crea una copia temporal de una variable izquierda cuando la expresión derecha podría modificarla.
- Etiquetas: `while0`, `else1`, `endfor2`, etc. Únicas en toda la unidad; los saltos siempre apuntan a etiquetas existentes.
- Las funciones globales se nombran `nombre@sIDdelÁmbitoContenedor`; los métodos `Clase.método`; las definiciones se escriben tras el bloque `main` y **son secciones de código, no llamadas implícitas**.
- Se representa la precedencia y el orden de evaluación según el árbol de ANTLR. Los literales string conservan sus comillas.
- Las expresiones pueden reutilizar un temporal como destino después de que sus valores anteriores hayan dejado de necesitarse.

## Instrucciones y semántica abstracta

| Forma | Significado |
| --- | --- |
| `declare x@sN` | Reserva abstracta de variable sin valor inicial |
| `x@sN = y` | Copia / asignación a variable o temporal |
| `t = a + b` (`-`, `*`, `/`, `%`) | Operación aritmética de tres direcciones |
| `t = a == b` (`!=`, `<`, `<=`, `>`, `>=`) | Comparación; produce boolean |
| `t = -x`, `t = !x` | Operador unario |
| `L:` | Etiqueta de control |
| `goto L`, `if x goto L`, `ifFalse x goto L` | Saltos incondicionales y condicionales |
| `t = new_array n`, `t[i] = v`, `t = a[i]` | Creación, escritura y lectura de arreglos |
| `t = length a` | Longitud del arreglo para `foreach` |
| `param x`, `t = call nombre@sN, n` | Preparación de argumentos y llamada con `n` parámetros |
| `t = callmethod obj.metodo, n` | Despacho de método (resolución dinámica de herencia) |
| `func nombre(params):` / `endfunc nombre` | Delimita el cuerpo compilado de función/método |
| `return x` / `return` | Devuelve resultado o finaliza el frame |
| `class H extends P`, `field H.x`, `endclass H` | Declaración de clase, padre y layout propio |
| `t = new H`, `init_fields t, H` | Reserva un objeto e inicializa campos **de la jerarquía, de padre a hijo** |
| `func H.$fields(this):` | Sección diferida que evalúa las expresiones inicializadoras de campos de **cada instancia** |
| `t = obj.campo`, `obj.campo = v` | Lectura/escritura de atributo |
| `f = closure etiqueta env sN` | Construye cierre capturando entorno léxico `sN` |
| `push_handler L`, `pop_handler`, `catch ex` | Instala, restaura y entra al manejador de excepciones |
| `print v` | Operación abstracta de salida, **no ejecutada** por el compilador |

Los opcodes declarativos o especializados (`CLASS`, `INIT_FIELDS`, `CLOSURE`, `TRY`) permanecen como primitivas abstractas del IR. No implican que exista un intérprete ni un asignador de memoria real. Un backend futuro deberá definir su representación de bajo nivel y la convención de llamadas. La tabla de símbolos contiene los offsets para facilitar esa fase futura.

## Ejemplo 1. Expresiones y reciclaje

Entrada:

```cps
let a: integer = 10;
let b: integer = 5;
let c: integer = (a + b) * 2 - 1;
```

TAC representativo (los números concretos de temporales pueden variar):

```text
main:
a@s0 = 10
b@s0 = 5
t0 = a@s0 + b@s0
t0 = t0 * 2
t0 = t0 - 1
c@s0 = t0
return
```

`TemporaryPool` gestiona temporales **por frame**. En `a+b` se reserva `t0`; las operaciones subsiguientes sobrescriben ese temporal cuando su valor anterior deja de estar vivo. Una vez que se asigna `c`, `t0` se libera; otra operación independiente puede volver a reservarlo. Las llamadas anidadas o expresiones con dos valores vivos pueden requerir simultáneamente `t0`, `t1`, etc. El contador de reutilizaciones incluye ambos tipos de reciclaje.

## Ejemplo 2. Cortocircuito

Entrada:

```cps
let ok: boolean = a > 0 && b > 0;
```

Esquema del TAC:

```text
t0 = a@s0 > 0
t1 = t0
ifFalse t1 goto shortcircuit0
t0 = b@s0 > 0
t1 = t0
shortcircuit0:
ok@s0 = t1
```

La evaluación del segundo operando **queda detrás de un salto**. Con `||` se utiliza `if ... goto`. Esto conserva la semántica de cortocircuito incluso cuando el segundo operando es una llamada a una función con efectos laterales.

## Ejemplo 3. Funciones, recursividad y frames

```cps
function factorial(n: integer): integer {
  if (n <= 1) { return 1; }
  else { return n * factorial(n - 1); }
}
let respuesta: integer = factorial(5);
```

El TAC emite una sección `func factorial@s0(n@s1):`, evalúa el caso base mediante saltos y emite `param ...; t = call factorial@s0, 1` en el paso recursivo. El destino de la llamada es la **misma etiqueta de función**, pero cada invocación crea conceptualmente **otro registro de activación** con parámetros y temporales nuevos. El programa principal solo contiene la llamada inicial y su resultado.

Los parámetros usan offsets `FP+16`, `FP+24`... y las variables locales `FP-8`, `FP-16`... bajo la convención abstracta de slots de 8 bytes. El frame contiene su propio banco `t0`, `t1`, etc. Las funciones anidadas pueden emitir `closure etiqueta env sN` para capturar el ámbito contenedor.

## Ejemplo 4. Clases y herencia

```cps
class Base { let x: integer = 1; }
class Hija : Base { let y: integer = 2 + 3; }
let obj: Hija = new Hija();
```

La tabla de símbolos da offset 0 al campo `Base.x` y offset 8 al campo `Hija.y`. El TAC incluye declaraciones de clase/campos, `new Hija`, `init_fields obj, Hija` y las secciones diferidas `Base.$fields` y `Hija.$fields`. La primitiva `init_fields` implica inicializar los campos de la clase base antes de la derivada, **en cada creación de objeto**. Los métodos se definen como `func Clase.método`; `callmethod` resuelve la clase real del receptor y permite usar métodos heredados. Una llamada a `constructor` se produce si corresponde, con los parámetros correspondientes.

## Ejemplo 5. Manejo de excepciones

```cps
try { print(lista[100]); }
catch (err) { print(err); }
```

```text
push_handler catch0
...
pop_handler
goto endtry1
catch0:
catch err@s1
...
endtry1:
```

El código protegido instala el manejador y lo retira al salir normalmente; una excepción abstracta transfiere control a la etiqueta `catch`. `catch err` enlaza el valor de la excepción. No se implementa la ejecución real de excepciones.

## Sentencias de control

- `if / else`: `ifFalse condición goto else`, bloque verdadero, `goto end`, bloque falso y `end`.
- `while`: etiqueta de condición, salida con `ifFalse`, cuerpo y salto a condición.
- `do-while`: etiqueta del cuerpo, etiqueta propia para `continue`, condición final y salto al comienzo.
- `for`: inicializador, condición, cuerpo, etiqueta del paso para `continue`, incremento, vuelta al test y salida.
- `foreach`: evalúa el arreglo **una sola vez**, reserva índice y longitud, asigna el elemento al identificador de iteración e incrementa el índice.
- `switch`: compara el discriminante con cada `case`, salta al caso encontrado, permite caída al siguiente caso cuando no existe `break`; `break` salta a `endswitch`. Se admiten valores escalares `integer`, `float`, `string` y `boolean`.
- `break` y `continue`: dos pilas de etiquetas separadas; `break` también es válido dentro de `switch`, mientras `continue` requiere un ciclo.
- Ternario: condicional con dos ramas que escriben un temporal compartido y confluyen en una etiqueta de fin.

## Política de errores y supuestos

Si ANTLR detecta errores léxicos o sintácticos, no se hace análisis semántico y no se construye TAC. Si el análisis semántico encuentra algún error, igualmente **no** se construye TAC. Un fallo imprevisto del traductor se convierte en un diagnóstico `TAC_UNSUPPORTED` y se descarta cualquier TAC parcial. El IR solo representa programas estáticamente aceptados, no comprueba en tiempo de ejecución índices fuera de rango, división por cero, parámetros dinámicos ni excepciones ejecutadas.

Extensiones heredadas: `float` y el parseo tolerante de `const` sin inicialización (rechazado luego semánticamente). El resto de la construcción sigue la gramática adjunta y el contrato de generación de CI facilitado por la cátedra.

## Trazabilidad de la rúbrica

| Categoría | Módulos y pruebas asociadas |
| --- | --- |
| Diseño del IR | `tac_ir.py`, este documento |
| Variables y constantes | `visitVariableDeclaration`, `visitConstantDeclaration`, `01_variables.cps` |
| Aritmética y lógica | `_binary_chain`, `_logical`, `02_*.cps`–`04_*.cps` |
| Arreglos | `visitArrayLiteral`, `visitLeftHandSide`, `05_*.cps`, `06_*.cps`, `27_*.cps` |
| Control de flujo | Visitas `If/While/DoWhile/For/Foreach/Switch`, `08_*.cps`–`13_*.cps` |
| Funciones y recursividad | `visitFunctionDeclaration`, `_function_body`, `15_*.cps`, `16_*.cps`, `28_*.cps` |
| Clases, objetos, herencia | `visitClassDeclaration`, `_field_initializer_body`, `visitNewExpr`, `17_*.cps`, `18_*.cps` |
| `try/catch` | `visitTryCatchStatement`, `14_try_catch.cps` |
| Reciclaje | `TemporaryPool`, `_binary_chain`, `21_operacion_reciclaje.cps` |
| Tabla de símbolos | `SymbolTable.plan_storage`, prueba de invariantes |

La rúbrica local suministrada suma 25 puntos; la especificación pública enlazada formula el mismo trabajo general con una ponderación distinta de 100 puntos. Los archivos se prepararon según las categorías funcionales de la rúbrica local.

## Precisión de orden de evaluación y saltos desde `try`

Las referencias de variables (`a@sN`) son posiciones de almacenamiento, no valores congelados. En `a + (a = 3)`, antes de evaluar el segundo sumando se emite `t0 = a@sN`; después se realiza `a@sN = 3` y la suma utiliza `t0 + 3`. La misma precaución se aplica a argumentos de llamada, referencias de arreglo, índices y receptores de métodos que pueden cambiar durante la evaluación de otro argumento. Los temporales usados para estas copias no se liberan antes de su último uso. Los argumentos de `new Clase(...)` se evalúan y congelan ANTES de `NEW` y `INIT_FIELDS`, de modo que sus efectos laterales ocurran antes de los inicializadores de campos y del constructor.

En un `for`, los puntos y coma directos del encabezado separan la condición opcional del incremento opcional. Por ello, `for (; ; x = x + 1)` no trata el incremento como condición booleana: el comienzo del ciclo no emite un `ifFalse` y el incremento queda bajo `forstep` (el destino de `continue`).

El traductor mantiene una pila de manejadores `TRY` activos y memoriza su profundidad cuando entra en un ciclo o `switch`. Cuando `return`, `break` o `continue` abandona uno o varios bloques `try`, emite un `pop_handler` por cada manejador que deja atrás. Si el salto permanece *dentro* del mismo `try`, su manejador continúa activo. Una ruta que ya hizo `return` puede estar seguida de código inalcanzable emitido para la salida normal del bloque; la representación estática no ejecuta ese código.

La nueva batería estructural verifica estos invariantes, el orden de los operandos y los destinos de todas las etiquetas de salto. Se conserva el carácter **abstracto** del TAC sin crear un intérprete ni ensamblador.
