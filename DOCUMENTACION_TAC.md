# EspecificaciÃ³n del cÃ³digo intermedio (TAC)

**Ãmbito:** traducciÃ³n estÃ¡tica de Compiscript a un IR de tres direcciones, sin ejecuciÃ³n ni generaciÃ³n de cÃ³digo objeto. Su sintaxis es una decisiÃ³n del grupo, permitida por la especificaciÃ³n oficial. Cada `Instruction` conserva opcode, argumentos y lÃ­nea de origen cuando se dispone de ella; la vista del IDE muestra instrucciones numeradas y la exportaciÃ³n conserva la misma numeraciÃ³n.

## Convenciones

- Variables: `nombre@sID`, donde `ID` identifica el Ã¡mbito semÃ¡ntico y evita colisiones por sombreado. Ej.: `x@s0`, `x@s2`.
- Temporales: `t0`, `t1`... propios de cada funciÃ³n o del `main`. Se pueden volver a utilizar tras su Ãºltimo uso o sobrescribir en una operaciÃ³n `t0 = t0 + ...`. Se crea una copia temporal de una variable izquierda cuando la expresiÃ³n derecha podrÃ­a modificarla.
- Etiquetas: `while0`, `else1`, `endfor2`, etc. Ãšnicas en toda la unidad; los saltos siempre apuntan a etiquetas existentes.
- Las funciones globales se nombran `nombre@sIDdelÃmbitoContenedor`; los mÃ©todos `Clase.mÃ©todo`; las definiciones se escriben tras el bloque `main` y **son secciones de cÃ³digo, no llamadas implÃ­citas**.
- Se representa la precedencia y el orden de evaluaciÃ³n segÃºn el Ã¡rbol de ANTLR. Los literales string conservan sus comillas.
- Las expresiones pueden reutilizar un temporal como destino despuÃ©s de que sus valores anteriores hayan dejado de necesitarse.

## Instrucciones y semÃ¡ntica abstracta

| Forma | Significado |
| --- | --- |
| `declare x@sN` | Reserva abstracta de variable sin valor inicial |
| `x@sN = y` | Copia / asignaciÃ³n a variable o temporal |
| `t = a + b` (`-`, `*`, `/`, `%`) | OperaciÃ³n aritmÃ©tica de tres direcciones |
| `t = a == b` (`!=`, `<`, `<=`, `>`, `>=`) | ComparaciÃ³n; produce boolean |
| `t = -x`, `t = !x` | Operador unario |
| `L:` | Etiqueta de control |
| `goto L`, `if x goto L`, `ifFalse x goto L` | Saltos incondicionales y condicionales |
| `t = new_array n`, `t[i] = v`, `t = a[i]` | CreaciÃ³n, escritura y lectura de arreglos |
| `t = length a` | Longitud del arreglo para `foreach` |
| `param x`, `t = call nombre@sN, n` | PreparaciÃ³n de argumentos y llamada con `n` parÃ¡metros |
| `t = callmethod obj.metodo, n` | Despacho de mÃ©todo (resoluciÃ³n dinÃ¡mica de herencia) |
| `func nombre(params):` / `endfunc nombre` | Delimita el cuerpo compilado de funciÃ³n/mÃ©todo |
| `return x` / `return` | Devuelve resultado o finaliza el frame |
| `class H extends P`, `field H.x`, `endclass H` | DeclaraciÃ³n de clase, padre y layout propio |
| `t = new H`, `init_fields t, H` | Reserva un objeto e inicializa campos **de la jerarquÃ­a, de padre a hijo** |
| `func H.$fields(this):` | SecciÃ³n diferida que evalÃºa las expresiones inicializadoras de campos de **cada instancia** |
| `t = obj.campo`, `obj.campo = v` | Lectura/escritura de atributo |
| `f = closure etiqueta env sN` | Construye cierre capturando entorno lÃ©xico `sN` |
| `push_handler L`, `pop_handler`, `catch ex` | Instala, restaura y entra al manejador de excepciones |
| `print v` | OperaciÃ³n abstracta de salida, **no ejecutada** por el compilador |

Los opcodes declarativos o especializados (`CLASS`, `INIT_FIELDS`, `CLOSURE`, `TRY`) permanecen como primitivas abstractas del IR. No implican que exista un intÃ©rprete ni un asignador de memoria real. Un backend futuro deberÃ¡ definir su representaciÃ³n de bajo nivel y la convenciÃ³n de llamadas. La tabla de sÃ­mbolos contiene los offsets para facilitar esa fase futura.

## Ejemplo 1. Expresiones y reciclaje

Entrada:

```cps
let a: integer = 10;
let b: integer = 5;
let c: integer = (a + b) * 2 - 1;
```

TAC representativo (los nÃºmeros concretos de temporales pueden variar):

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

`TemporaryPool` gestiona temporales **por frame**. En `a+b` se reserva `t0`; las operaciones subsiguientes sobrescriben ese temporal cuando su valor anterior deja de estar vivo. Una vez que se asigna `c`, `t0` se libera; otra operaciÃ³n independiente puede volver a reservarlo. Las llamadas anidadas o expresiones con dos valores vivos pueden requerir simultÃ¡neamente `t0`, `t1`, etc. El contador de reutilizaciones incluye ambos tipos de reciclaje.

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

La evaluaciÃ³n del segundo operando **queda detrÃ¡s de un salto**. Con `||` se utiliza `if ... goto`. Esto conserva la semÃ¡ntica de cortocircuito incluso cuando el segundo operando es una llamada a una funciÃ³n con efectos laterales.

## Ejemplo 3. Funciones, recursividad y frames

```cps
function factorial(n: integer): integer {
  if (n <= 1) { return 1; }
  else { return n * factorial(n - 1); }
}
let respuesta: integer = factorial(5);
```

El TAC emite una secciÃ³n `func factorial@s0(n@s1):`, evalÃºa el caso base mediante saltos y emite `param ...; t = call factorial@s0, 1` en el paso recursivo. El destino de la llamada es la **misma etiqueta de funciÃ³n**, pero cada invocaciÃ³n crea conceptualmente **otro registro de activaciÃ³n** con parÃ¡metros y temporales nuevos. El programa principal solo contiene la llamada inicial y su resultado.

Los parÃ¡metros usan offsets `FP+16`, `FP+24`... y las variables locales `FP-8`, `FP-16`... bajo la convenciÃ³n abstracta de slots de 8 bytes. El frame contiene su propio banco `t0`, `t1`, etc. Las funciones anidadas pueden emitir `closure etiqueta env sN` para capturar el Ã¡mbito contenedor.

## Ejemplo 4. Clases y herencia

```cps
class Base { let x: integer = 1; }
class Hija : Base { let y: integer = 2 + 3; }
let obj: Hija = new Hija();
```

La tabla de sÃ­mbolos da offset 0 al campo `Base.x` y offset 8 al campo `Hija.y`. El TAC incluye declaraciones de clase/campos, `new Hija`, `init_fields obj, Hija` y las secciones diferidas `Base.$fields` y `Hija.$fields`. La primitiva `init_fields` implica inicializar los campos de la clase base antes de la derivada, **en cada creaciÃ³n de objeto**. Los mÃ©todos se definen como `func Clase.mÃ©todo`; `callmethod` resuelve la clase real del receptor y permite usar mÃ©todos heredados. Una llamada a `constructor` se produce si corresponde, con los parÃ¡metros correspondientes.

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

El cÃ³digo protegido instala el manejador y lo retira al salir normalmente; una excepciÃ³n abstracta transfiere control a la etiqueta `catch`. `catch err` enlaza el valor de la excepciÃ³n. No se implementa la ejecuciÃ³n real de excepciones.

## Sentencias de control

- `if / else`: `ifFalse condiciÃ³n goto else`, bloque verdadero, `goto end`, bloque falso y `end`.
- `while`: etiqueta de condiciÃ³n, salida con `ifFalse`, cuerpo y salto a condiciÃ³n.
- `do-while`: etiqueta del cuerpo, etiqueta propia para `continue`, condiciÃ³n final y salto al comienzo.
- `for`: inicializador, condiciÃ³n, cuerpo, etiqueta del paso para `continue`, incremento, vuelta al test y salida.
- `foreach`: evalÃºa el arreglo **una sola vez**, reserva Ã­ndice y longitud, asigna el elemento al identificador de iteraciÃ³n e incrementa el Ã­ndice.
- `switch`: compara el discriminante con cada `case`, salta al caso encontrado, permite caída al siguiente caso cuando no existe `break`; `break` salta a `endswitch`. Se admiten valores escalares oficiales `integer`, `string` y `boolean`.
- `break` y `continue`: dos pilas de etiquetas separadas; `break` tambiÃ©n es vÃ¡lido dentro de `switch`, mientras `continue` requiere un ciclo.
- Ternario: condicional con dos ramas que escriben un temporal compartido y confluyen en una etiqueta de fin.

## PolÃ­tica de errores y supuestos

Si ANTLR detecta errores lÃ©xicos o sintÃ¡cticos, no se hace anÃ¡lisis semÃ¡ntico y no se construye TAC. Si el anÃ¡lisis semÃ¡ntico encuentra algÃºn error, igualmente **no** se construye TAC. Un fallo imprevisto del traductor se convierte en un diagnÃ³stico `TAC_UNSUPPORTED` y se descarta cualquier TAC parcial. El IR solo representa programas estÃ¡ticamente aceptados, no comprueba en tiempo de ejecuciÃ³n Ã­ndices fuera de rango, divisiÃ³n por cero, parÃ¡metros dinÃ¡micos ni excepciones ejecutadas.

El traductor opera en modo estándar sobre la gramática oficial: no acepta `float` nativo y `const` sin inicializador es error sintáctico. El TAC se genera únicamente para programas aceptados por esa gramática y por el análisis semántico.

## Trazabilidad de la rÃºbrica

| CategorÃ­a | MÃ³dulos y pruebas asociadas |
| --- | --- |
| DiseÃ±o del IR | `tac_ir.py`, este documento |
| Variables y constantes | `visitVariableDeclaration`, `visitConstantDeclaration`, `01_variables.cps` |
| AritmÃ©tica y lÃ³gica | `_binary_chain`, `_logical`, `02_*.cps`â€“`04_*.cps` |
| Arreglos | `visitArrayLiteral`, `visitLeftHandSide`, `05_*.cps`, `06_*.cps`, `27_*.cps` |
| Control de flujo | Visitas `If/While/DoWhile/For/Foreach/Switch`, `08_*.cps`â€“`13_*.cps` |
| Funciones y recursividad | `visitFunctionDeclaration`, `_function_body`, `15_*.cps`, `16_*.cps`, `28_*.cps` |
| Clases, objetos, herencia | `visitClassDeclaration`, `_field_initializer_body`, `visitNewExpr`, `17_*.cps`, `18_*.cps` |
| `try/catch` | `visitTryCatchStatement`, `14_try_catch.cps` |
| Reciclaje | `TemporaryPool`, `_binary_chain`, `21_operacion_reciclaje.cps` |
| Tabla de sÃ­mbolos | `SymbolTable.plan_storage`, prueba de invariantes |

La rÃºbrica local suministrada suma 25 puntos; la especificaciÃ³n pÃºblica enlazada formula el mismo trabajo general con una ponderaciÃ³n distinta de 100 puntos. Los archivos se prepararon segÃºn las categorÃ­as funcionales de la rÃºbrica local.

## PrecisiÃ³n de orden de evaluaciÃ³n y saltos desde `try`

Las referencias de variables (`a@sN`) son posiciones de almacenamiento, no valores congelados. En `a + (a = 3)`, antes de evaluar el segundo sumando se emite `t0 = a@sN`; despuÃ©s se realiza `a@sN = 3` y la suma utiliza `t0 + 3`. La misma precauciÃ³n se aplica a argumentos de llamada, referencias de arreglo, Ã­ndices y receptores de mÃ©todos que pueden cambiar durante la evaluaciÃ³n de otro argumento. Los temporales usados para estas copias no se liberan antes de su Ãºltimo uso. Los argumentos de `new Clase(...)` se evalÃºan y congelan ANTES de `NEW` y `INIT_FIELDS`, de modo que sus efectos laterales ocurran antes de los inicializadores de campos y del constructor.

En un `for`, los puntos y coma directos del encabezado separan la condiciÃ³n opcional del incremento opcional. Por ello, `for (; ; x = x + 1)` no trata el incremento como condiciÃ³n booleana: el comienzo del ciclo no emite un `ifFalse` y el incremento queda bajo `forstep` (el destino de `continue`).

El traductor mantiene una pila de manejadores `TRY` activos y memoriza su profundidad cuando entra en un ciclo o `switch`. Cuando `return`, `break` o `continue` abandona uno o varios bloques `try`, emite un `pop_handler` por cada manejador que deja atrÃ¡s. Si el salto permanece *dentro* del mismo `try`, su manejador continÃºa activo. Una ruta que ya hizo `return` puede estar seguida de cÃ³digo inalcanzable emitido para la salida normal del bloque; la representaciÃ³n estÃ¡tica no ejecuta ese cÃ³digo.

La nueva baterÃ­a estructural verifica estos invariantes, el orden de los operandos y los destinos de todas las etiquetas de salto. Se conserva el carÃ¡cter **abstracto** del TAC sin crear un intÃ©rprete ni ensamblador.
