# Generación de código MIPS — Proyecto 3

Este documento describe el backend que traduce el código de tres direcciones (TAC) del Proyecto 2 a ensamblador MIPS32 ejecutable en **MARS 4.5**, **SPIM** y **QtSpim**, y el simulador integrado que usa el IDE. La arquitectura general del compilador está en `DOCUMENTACION_ARQUITECTURA.md`.

## 1. Flujo del backend

```text
TACProgram (Proyecto 2, con tipos por instrucción)
        │
        ▼
mips_analysis.py   unidades de código · bloques básicos · grafo de flujo (con aristas a catch)
                   · variables vivas y siguiente uso · fusión "t = op; x = t"
        │
        ▼
mips_frames.py     dueño de cada variable · capturas por funciones anidadas · enlace de acceso
                   · registros $s por función · diseño del registro de activación
                   · diseño de objetos y tablas de métodos (vtables)
        │
        ▼
mips_codegen.py    traducción instrucción por instrucción, prólogos/epílogos, llamadas
   + mips_regalloc.py   getReg() con descriptores de registro y de dirección
   + mips_runtime.py    biblioteca en MIPS (print, cadenas, arreglos, objetos, excepciones)
        │
        ▼
mips_peephole.py   optimización por mirilla (11 transformaciones) + reporte
        │
        ▼
mips_backend.py    MIPSResult: .asm final, .asm sin optimizar, reportes, run()
        │
        ├── mips_simulator.py  simulador integrado + árbol de activación (IDE y pruebas)
        └── mips_external.py   MARS (herramientas/Mars4_5.jar) y SPIM reales
```

El backend solo se invoca cuando no hay errores léxicos, sintácticos ni semánticos. Si una construcción válida no puede traducirse, el analizador devuelve el diagnóstico `MIPS_UNSUPPORTED` (tipo «Generación») y no se entrega un `.asm` parcial; el TAC sigue visible para revisarlo.

## 2. Cambios necesarios en las fases anteriores

| Cambio | Motivo |
| --- | --- |
| Cada `Instruction` del TAC conserva `types` (tipos estáticos) y `note`; `TACProgram.functions` guarda metadatos de cada función (`FunctionInfo`). La forma textual del TAC no cambia. | El backend necesita distinguir suma entera de concatenación, elegir la rutina de `print` y resolver campos/métodos según la clase estática. |
| El analizador semántico anota `_expr_type` en cada nodo de expresión. | Fuente de los tipos anteriores. |
| `string + integer/boolean` es válido y concatena con conversión implícita. | El programa de ejemplo oficial usa `print("5 + 1 = " + addFive)`; sin esto no compilaba. `-`, `*`, `/` y `%` con cadenas siguen siendo errores (prueba `61_*`). |
| Una instancia de una clase derivada se acepta donde se espera la base (variables, parámetros, arreglos). | Polimorfismo necesario para demostrar despacho dinámico en herencia. La asignación inversa sigue siendo error (prueba `60_*`). |
| La variable de `catch` es de tipo `string`. | En ejecución recibe el mensaje del error. |
| Los miembros usados sin `this.` dentro de un método (`cuenta = cuenta + paso`) se traducen como acceso a `this`. | Antes generaban nombres de campo sin objeto. |

Las 138 verificaciones de los proyectos 1 y 2 siguen pasando; se agregaron 4 pruebas semánticas para las dos reglas nuevas.

## 3. Registros de activación y secuencias de llamada/retorno

### 3.1 Forma del registro de activación

La pila crece hacia direcciones bajas. `$fp` apunta a la base del marco (el `$sp` del llamador antes de la llamada).

```text
   direcciones altas
   ┌────────────────────────────────────────┐
   │ argumento 6                 4($fp)     │  ← apilados por el llamador
   │ argumento 5                 0($fp)     │    (solo a partir del 5.º)
   ├────────────────────────────────────────┤ ← $fp
   │ dirección de retorno $ra   -4($fp)     │
   │ $fp del llamador           -8($fp)     │  enlace de control
   │ enlace de acceso          -12($fp)     │  solo funciones anidadas
   │ registros $s preservados               │  callee-saved
   │ variables locales en memoria           │  capturadas / sin registro
   │ registros try/catch (16 bytes c/u)     │  anterior, dirección, $sp, $fp
   │ temporales derramados / caller-saved   │
   └────────────────────────────────────────┘ ← $sp   (tamaño múltiplo de 8)
   direcciones bajas
```

La pestaña **Registros** del IDE y `python compilar_cli.py archivo.cps --reporte` muestran el marco real de cada función, con ubicaciones concretas.

### 3.2 Lado del llamador (`op_CALL`, `op_CALL_METHOD`)

1. Guarda en su marco los temporales `$t` que siguen vivos después de la llamada (los `$t` no se preservan).
2. Si hay más de cuatro argumentos, reserva espacio y apila del 5.º en adelante; los cuatro primeros van en `$a0`–`$a3`. En los métodos, `$a0` es `this`.
3. Si el destino es una función anidada, pasa en `$v1` el enlace de acceso (el `$fp` del marco que la declaró, siguiendo enlaces si hace falta).
4. `jal etiqueta` para funciones; para métodos, verificación de receptor nulo y `lw $t8, 0($a0)` → `lw $t9, desplazamiento($t8)` → `jalr $t9` (despacho dinámico).
5. Libera los argumentos apilados y toma el resultado de `$v0`.

### 3.3 Lado del llamado (prólogo y epílogo)

```asm
fn_factorial:
    addiu  $sp, $sp, -16        # prólogo: reserva el registro de activación
    sw     $ra, 12($sp)         # dirección de retorno
    sw     $fp, 8($sp)          # enlace de control
    addiu  $fp, $sp, 16         # $fp = base del marco
    sw     $s0, -12($fp)        # preserva $s0 (callee-saved)
    move   $s0, $a0             # parámetro n
    ...
    mul    $v0, $t1, $t0        # resultado en $v0
fn_factorial_fin:
    lw     $s0, -12($fp)        # epílogo: restaura registros preservados
    lw     $ra, 12($sp)
    lw     $fp, 8($sp)
    addiu  $sp, $sp, 16         # libera el marco
    jr     $ra
```

Cada `return` deja el valor en `$v0` y salta al epílogo único de la función. Como cada llamada reserva su propio marco, la recursión (simple y mutua) funciona sin compartir parámetros ni locales; `test_prologo_y_epilogo_balanceados` verifica que todo prólogo tenga su epílogo simétrico.

### 3.4 Funciones anidadas y variables globales

* Las variables de una función que son usadas por funciones anidadas viven en memoria (no en `$s`). La función anidada recibe el **enlace de acceso** en `$v1`, lo guarda en `-12($fp)` y lo sigue *n* veces para llegar a la variable (`lw $t8, -12($fp)` / `lw $t8, -12($t8)` …). `14_closures.cps` prueba uno y dos niveles, y una función anidada recursiva.
* Las variables del programa principal sin registro `$s`, o usadas desde funciones, viven en `.data` (`g_nombre`). Las clases declaradas dentro de una función no pueden capturar variables locales: se rechaza con `MIPS_UNSUPPORTED` (prueba `25_*`).

### 3.5 Árbol de activación

El simulador integrado observa cada `jal`/`jalr` hacia la entrada de una función y cada `jr $ra` de un epílogo. Con eso construye el árbol de activación de la ejecución real: nombre, argumentos (leídos de `$a0`–`$a3` y de la pila), valor de retorno (`$v0`) y estado (*retornó*, *excepción*, *activa*). Cuando una excepción descarta marcos, las activaciones abandonadas se marcan como «terminada por una excepción». El IDE lo muestra en la pestaña **Activación**; la consola con `--arbol`:

```text
main()
├── fib(n=4) → 3
│   ├── fib(n=3) → 2
│   │   ├── fib(n=2) → 1
│   │   │   ├── fib(n=1) → 1
│   │   │   └── fib(n=0) → 0
│   │   └── fib(n=1) → 1
│   └── fib(n=2) → 1
│       ├── fib(n=1) → 1
│       └── fib(n=0) → 0
└── compuesto(x=3) → 14
    ├── doble(x=3) → 6
    └── doble(x=4) → 8
```

## 4. Asignación de registros: `getReg()`

| Registros | Uso |
| --- | --- |
| `$s0`–`$s7` | Variables locales y parámetros más usados de cada función (ponderados ×10 por nivel de ciclo). Fijos durante la función; se guardan en el prólogo y se restauran en el epílogo. |
| `$t0`–`$t7` | Temporales y copias en caché, administrados por `getReg()` por bloque básico. |
| `$t8`, `$t9` | Auxiliares del generador (direcciones, constantes, saltos indirectos). Nunca vivos entre instrucciones TAC. |
| `$a0`–`$a3`, `$v0`, `$v1` | Argumentos, resultados y enlace de acceso. |

`RegisterAllocator` (en `mips_regalloc.py`) mantiene:

* **Descriptor de registro**: qué nombres contiene cada `$t`.
* **Descriptor de dirección**: en qué registros está cada nombre y si su copia en memoria está desactualizada (`dirty`).

`getReg()`:

1. Si un operando de la instrucción actual muere en ella, el destino **reutiliza su registro** (`t = a + b` con `a` muerto → mismo registro).
2. Si no, entrega un `$t` libre.
3. Si no hay libres, elige una **víctima**: primero la que no necesita guardarse (valor muerto o ya en memoria) y, entre las demás, la de **siguiente uso más lejano** (información de vida calculada en `mips_analysis.py`). La víctima se derrama (*spill*) en su celda del registro de activación.

Además, los temporales vivos se guardan al final de cada bloque básico, antes de cada llamada (*caller-saved*) y antes de una operación que puede lanzar una excepción hacia un `catch` que los necesita. Las copias `x = t` no generan código: `x` pasa a compartir el registro (*alias*). Las variables con hogar en memoria se escriben de inmediato (*write-through*) y el registro queda como caché de lectura.

`18_presion_registros.cps` fuerza más valores vivos que registros: el reporte muestra 8 derrames, 8 `$t` ocupados a la vez y 26 destinos que heredan el registro de un operando muerto. La pestaña **Registros** del IDE muestra estas estadísticas y la asignación `$s` de cada función.

## 5. Traducción de cada construcción

| TAC | MIPS generado |
| --- | --- |
| `x = c`, `x = y`, `declare x` | `li`/`la`/`move`, alias en registro; `declare` inicializa en 0 (null/false). |
| `t = a + b` (enteros) | `addu`/`subu`/`mul`; `addiu` con constante de 16 bits; plegado de constantes. |
| `t = a / b`, `t = a % b` | `beqz divisor, rt_err_div` + `div` + `mflo`/`mfhi` (truncado, como C/Java). |
| `t = s + x` (cadenas) | `rt_int_to_str` / `rt_bool_to_str` + `rt_concat` (nueva cadena en el heap). |
| `t = a < b; ifFalse t goto L` | Un solo salto condicional (`bge a, b, L`) cuando `t` no se usa después. |
| `==`, `<` … con cadenas | `rt_str_eq` (contenido) y `rt_str_cmp` (lexicográfico). |
| `&&`, `\|\|` | Saltos de cortocircuito del TAC → `beqz`/`bnez`. |
| `!x`, `-x` | `sltiu r, x, 1` / `subu r, $zero, x`. |
| `t = new_array n`, `t[i] = v`, `t = a[i]`, `length a` | Arreglo en el heap `[longitud][e0][e1]…`; verificación de nulo y de límites (`sltu` sin signo cubre índices negativos). |
| `goto`, `if`, `ifFalse`, etiquetas | `j`, `bnez`, `beqz`. Cubre if/else, while, do-while, for, foreach, switch, ternario, break y continue. |
| `param`, `call`, `return` | Secuencias de la sección 3. |
| `t = new C`, `init_fields t, C` | `rt_new_object(vtable, tamaño)`; luego los inicializadores de campos de la jerarquía, de la raíz a la hoja. |
| `obj.campo`, `obj.campo = v` | `lw`/`sw` con el desplazamiento del campo (campos heredados primero). |
| `callmethod obj.m, n` | Despacho dinámico por vtable con `jalr`. |
| `print v` | `rt_print_int`, `rt_print_bool`, `rt_print_str` o `rt_print_any` (arreglos anidados y objetos). |
| `push_handler L`, `pop_handler`, `catch e` | Registro de manejador en el marco + `rt_eh_top`; ver sección 7. |

## 6. Representación de datos

* **Enteros y booleanos**: palabra de 32 bits (`true = 1`, `false = 0`); el desbordamiento sigue la aritmética de 32 bits (`2147483647 + 1 = -2147483648`).
* **Cadenas**: punteros a cadenas terminadas en `\0`, en `.data` (literales) o en el heap (`sbrk`). Caracteres como `ñ` se emiten con `.byte`.
* **`null`**: la palabra 0. Leer un campo, indexar o invocar un método sobre `null` lanza «referencia nula».
* **Arreglos**: `[longitud][elemento0][elemento1]…`.
* **Objetos**: `[vtable][campos heredados…][campos propios…]`. La vtable empieza con el nombre de la clase y luego los métodos; un método sobrescrito ocupa la misma posición que en la clase base, por eso `mascota.hablar()` con `mascota: Animal` ejecuta `Cachorro.hablar` (prueba `16_herencia.cps`).

```asm
vt_Animal:   .word cls_Animal, Animal_constructor, Animal_hablar,   Animal_presentar, Animal_numeroPatas
vt_Cachorro: .word cls_Cachorro, Animal_constructor, Cachorro_hablar, Animal_presentar, Animal_numeroPatas, Perro_aprender
```

## 7. try/catch

Cada `try` reserva en el marco un registro de 16 bytes `[manejador anterior | dirección del catch | $sp | $fp]` y lo enlaza en la lista global `rt_eh_top`. Los errores del runtime (índice fuera de rango, división entre cero, referencia nula) llaman a `rt_throw`, que desapila el manejador activo, restaura `$sp` y `$fp` —descartando todos los marcos intermedios, aunque el error ocurra varias llamadas más abajo— y salta al `catch` con el mensaje en `$v0`. `break`, `continue` y `return` dentro de un `try` retiran los manejadores que abandonan (`pop_handler`). Sin manejador, `rt_uncaught` imprime `Error en tiempo de ejecucion no capturado: …` y termina con código 1 (servicio 17).

```asm
    la     $t8, L_catch0           # dirección del catch
    sw     $t8, -20($fp)
    sw     $sp, -16($fp)           # estado de la pila a restaurar
    sw     $fp, -12($fp)
    lw     $t8, rt_eh_top
    sw     $t8, -24($fp)           # manejador anterior
    addiu  $t8, $fp, -24
    sw     $t8, rt_eh_top          # este registro es el manejador activo
    ...                            # código protegido (beqz ... rt_err_null, bnez ... rt_err_index)
L_catch0:
    move   $s0, $v0                # catch e: mensaje de la excepción
```

Como `rt_throw` no ejecuta epílogos, las variables que el `catch` o el código posterior necesitan nunca se colocan en registros `$s` ni se dejan solo en `$t`: el análisis de vida incluye aristas excepcionales hacia el manejador y el asignador las mantiene en memoria.

## 8. Optimización por mirilla

`mips_peephole.py` recorre el ensamblador con una ventana de dos a tres instrucciones y repite las reglas hasta que ninguna aplica. Cada aplicación queda registrada (antes/después) y se muestra en la pestaña **Mirilla**.

| # | Transformación | Ejemplo |
| --- | --- | --- |
| 1 | Código inalcanzable | `j L` seguido de instrucciones sin etiqueta → se eliminan |
| 2 | Salto a la siguiente instrucción | `j L` / `beq …, L` con `L:` inmediatamente después → se elimina |
| 3 | Salto condicional sobre salto | `beq a,b,L1; j L2; L1:` → `bne a,b,L2; L1:` |
| 4 | Encadenamiento de saltos | salto a `L1` donde `L1: j L2` → salto directo a `L2` |
| 5 | Carga después de almacenar | `sw r, M; lw r, M` → se elimina la carga (o `move`) |
| 6 | Movimiento redundante | `move r, r`; `move a, b; move b, a` |
| 7 | Identidades algebraicas | `x + 0`, `x - 0`, `x * 1`, `x * 0`, desplazamiento de 0 |
| 8 | Reducción de fuerza | `li $t9, 8; mul r, x, $t9` → `sll r, x, 3` |
| 9 | Propagación de copia | `move t, s; addiu t, t, 4` → `addiu t, s, 4` |
| 10 | Resultado directo en `$v0` | `addu t, a, b; move $v0, t; (retorno)` → `addu $v0, a, b` |
| 11 | Etiquetas sin uso | etiquetas de control que ya nadie referencia |

Cada regla tiene su prueba unitaria aislada (`PeepholeTests`), y la batería exige que **al menos 6 transformaciones distintas** se apliquen sobre los programas de prueba (se aplican las 11). Todos los programas se ejecutan con y sin mirilla y deben producir exactamente la misma salida. El IDE permite desactivarla con la casilla «Optimización por mirilla».

## 9. Simulador integrado y simuladores externos

`mips_simulator.py` ensambla y ejecuta el subconjunto de MIPS que emite el compilador (instrucciones, pseudoinstrucciones `li`, `la`, `move`, `blt`, `bge`, …, directivas `.data`, `.text`, `.word`, `.asciiz`, `.byte` y los servicios 1, 4, 9, 10, 11 y 17) con el mismo mapa de memoria que MARS. Detecta referencias nulas, desbordamiento de pila (recursión infinita), límite de instrucciones (ciclos infinitos) y saltos inválidos.

El mismo `.asm` se ejecuta sin cambios en:

* **MARS 4.5** — incluido en `herramientas/Mars4_5.jar` (licencia MIT en `herramientas/MARS_LICENCIA.txt`). Requiere Java 8+.
  * Consola: `java -jar herramientas/Mars4_5.jar nc programa.asm`
  * Interfaz: `java -jar herramientas/Mars4_5.jar` → *File → Open* → *Run → Assemble* (F3) → *Run → Go* (F5).
* **SPIM**: `spim -file programa.asm`.
* **QtSpim**: *File → Reinitialize and Load File* → *Run* (F5).

`python verificar_mips.py --externo` ejecuta los 23 programas válidos en MARS y SPIM y comprueba que la salida sea idéntica a la del simulador integrado (lo es en todos).

## 10. Batería de pruebas del Proyecto 3

`pruebas_mips/` contiene 26 programas con su salida esperada en `manifest.json`:

| Rúbrica | Programas |
| --- | --- |
| Selección de registros (4) | `18_presion_registros` + `RegisterAllocationTests` |
| Registros y árboles de activación (5) | `12_*`, `13_*`, `14_closures`, `19_arbol_activacion` + `CallingSequenceTests` |
| Variables y constantes (1) | `01_variables_constantes` |
| Expresiones aritméticas (1) | `02_aritmetica`, `04_cadenas` |
| Expresiones lógicas (1) | `03_logica` |
| Arreglos (1) | `05_arreglos` |
| Sentencias de control (3) | `06_if_else`, `07_while_do_while`, `08_for`, `09_foreach`, `10_switch`, `11_ternario` |
| Funciones y parámetros (2) | `12_funciones_parametros` |
| Recursividad (2) | `13_recursion` |
| Clases y objetos (2) | `15_clases_objetos` |
| Herencia (2) | `16_herencia` + `ObjectModelTests` |
| try/catch (2) | `17_try_catch`, `20_*`, `21_*` (fallos en ejecución) |
| Mirilla (3) | `PeepholeTests` (11 reglas + mínimo de 6 en la batería) |
| Simulador (1) | Todos, en el simulador integrado y en MARS/SPIM con `--externo` |
| Casos fallidos de compilación | `23_error_semantico`, `24_error_sintactico`, `25_error_generacion` |
| Integración | `00_programa_ejemplo`, `22_programa_completo` |

Total: 26 programas + 29 pruebas unitarias = **55 verificaciones MIPS**, dentro de las **197** de `verificar_proyecto.py`. `verificar_interfaz.py` añade 19 comprobaciones del IDE real.

## 11. Limitaciones conocidas

* Las funciones no son valores de primera clase (la gramática no permite llamarlas desde una variable; el análisis semántico ya lo rechazaba).
* Una clase declarada dentro de una función no puede leer variables locales de esa función (`MIPS_UNSUPPORTED`).
* No hay recolector de basura: el heap crece con `sbrk` (las cadenas concatenadas no se liberan), igual que en la mayoría de los compiladores académicos sobre MARS/SPIM.
* Los comentarios del `.asm` se escriben sin tildes para evitar problemas de codificación en los simuladores.
