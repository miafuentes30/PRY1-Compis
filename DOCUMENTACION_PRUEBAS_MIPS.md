# Documentación de pruebas MIPS para la presentación

Esta guía reúne ejemplos breves para demostrar en clase el recorrido completo del compilador:

```text
Compiscript (.cps) → análisis → TAC → MIPS → simulador integrado / MARS
```

Las pruebas de demostración complementan la batería oficial. No forman parte de `manifest.json`, por lo que no modifican las 197 verificaciones del proyecto.

## 1. Preparación

Desde PowerShell, entrar en la raíz del proyecto y activar UTF-8 para que los árboles y reportes se impriman correctamente:

```powershell
cd C:\Users\miafu\Downloads\PRY1-Compis
$env:PYTHONIOENCODING = "utf-8"
```

Para usar MARS se necesita Java. Se puede comprobar con:

```powershell
java -version
```

El IDE se abre con:

```powershell
python .\main.py
```

## 2. Pruebas disponibles

| Archivo | Conceptos principales | Líneas de fuente |
| --- | --- | ---: |
| `26_basicos_control_clase.cps` | Variables, constantes, aritmética, lógica, `if/else` y `for` | 16 |
| `27_arreglos_ciclos_clase.cps` | Arreglos, asignación por índice y `foreach` | 12 |
| `28_funciones_recursion_clase.cps` | Funciones, parámetros, llamadas anidadas, recursividad y activaciones | 19 |
| `29_clases_herencia_clase.cps` | Clases, objetos, constructor, herencia y despacho dinámico | 26 |
| `30_excepciones_clase.cps` | `try/catch`, error de índice y restauración de la pila | 14 |
| `31_registros_clase.cps` | Presión de registros y derrames de `getReg()` | 9 |

Todas las pruebas fueron ejecutadas correctamente en el simulador integrado y en MARS 4.5.

## 3. Variables, expresiones y control de flujo

Archivo: `pruebas_mips/26_basicos_control_clase.cps`

Demuestra:

- declaración de una constante y variables;
- multiplicación, suma y comparaciones;
- expresión lógica con `&&`;
- selección mediante `if/else`;
- ciclo `for`.

Comando:

```powershell
python .\compilar_cli.py .\pruebas_mips\26_basicos_control_clase.cps --ejecutar --mars
```

Salida esperada:

```text
25
dentro del rango
1
2
3
```

Durante la explicación se puede señalar que las expresiones se convierten primero a TAC y después a instrucciones aritméticas, comparaciones y saltos de MIPS.

## 4. Arreglos y ciclos

Archivo: `pruebas_mips/27_arreglos_ciclos_clase.cps`

Demuestra:

- creación de un arreglo de enteros;
- escritura y lectura mediante índices;
- recorrido con `foreach`;
- acumulación y división entera;
- impresión completa de un arreglo mediante el runtime.

Comando:

```powershell
python .\compilar_cli.py .\pruebas_mips\27_arreglos_ciclos_clase.cps --ejecutar --mars
```

Salida esperada:

```text
[75, 80, 90]
245
81
```

En el MIPS se pueden mencionar la longitud guardada al inicio del arreglo, el desplazamiento de cuatro bytes por elemento y las verificaciones de índice.

## 5. Funciones, recursividad y árbol de activación

Archivo: `pruebas_mips/28_funciones_recursion_clase.cps`

Demuestra:

- paso de parámetros;
- retorno por `$v0`;
- llamadas normales y anidadas;
- recursividad con factorial;
- creación de un registro de activación por llamada;
- prólogos, epílogos y restauración de `$sp`, `$fp` y `$ra`.

Comando recomendado:

```powershell
python .\compilar_cli.py .\pruebas_mips\28_funciones_recursion_clase.cps --ejecutar --arbol --mars
```

Salida esperada:

```text
7
120
25
```

La ejecución realiza 12 llamadas y alcanza una profundidad máxima de 5. El árbol permite mostrar visualmente las activaciones de `factorial`, `calcular` y `sumar`.

Esta prueba también es conveniente para enseñar la optimización por mirilla:

```powershell
python .\compilar_cli.py .\pruebas_mips\28_funciones_recursion_clase.cps --reporte
```

La mirilla reduce el programa de 84 a 73 instrucciones MIPS.

## 6. Clases, objetos y herencia

Archivo: `pruebas_mips/29_clases_herencia_clase.cps`

Demuestra:

- definición de las clases `Animal` y `Perro`;
- atributo y constructor heredado;
- sobrescritura del método `hablar`;
- método heredado que invoca un método sobrescrito;
- polimorfismo mediante una variable de tipo `Animal` que contiene un `Perro`;
- despacho dinámico mediante vtable y `jalr`.

Comando:

```powershell
python .\compilar_cli.py .\pruebas_mips\29_clases_herencia_clase.cps --ejecutar --mars
```

Salida esperada:

```text
Luna
Soy Luna: Luna ladra
```

Para exportar el ensamblador e identificar las vtables y el salto indirecto:

```powershell
python .\compilar_cli.py .\pruebas_mips\29_clases_herencia_clase.cps --asm .\demostracion_clases.asm
Select-String -Path .\demostracion_clases.asm -Pattern "vt_|jalr"
```

## 7. Excepciones y restauración de la pila

Archivo: `pruebas_mips/30_excepciones_clase.cps`

Demuestra:

- bloque `try/catch`;
- error de índice fuera de rango dentro de una función;
- propagación de la excepción al llamador;
- descarte de la activación que falló;
- restauración de `$sp` y `$fp`;
- continuación normal después del `catch`.

Comando:

```powershell
python .\compilar_cli.py .\pruebas_mips\30_excepciones_clase.cps --ejecutar --arbol --mars
```

Salida esperada:

```text
capturado: indice de arreglo fuera de rango
el programa continua
```

## 8. Selección y derrame de registros

Archivo: `pruebas_mips/31_registros_clase.cps`

La expresión mantiene suficientes resultados parciales vivos para ocupar los ocho registros temporales administrados por `getReg()`.

Comando de ejecución:

```powershell
python .\compilar_cli.py .\pruebas_mips\31_registros_clase.cps --ejecutar --mars
```

Salida esperada:

```text
55
asignacion correcta
```

Comando para mostrar las estadísticas del asignador:

```powershell
python .\compilar_cli.py .\pruebas_mips\31_registros_clase.cps --reporte
```

Resultados importantes del reporte:

```text
13  Registros entregados por getReg()
 2  Derrames (spill) por falta de registros
 8  Máximo de registros $t ocupados a la vez
```

Los derrames guardan temporalmente valores en el registro de activación cuando no queda ningún `$t` disponible.

## 9. Orden recomendado para la exposición

### Presentación completa, 15 a 20 minutos

1. `26_basicos_control_clase.cps`: recorrido inicial del compilador.
2. `27_arreglos_ciclos_clase.cps`: memoria y validación de índices.
3. `28_funciones_recursion_clase.cps`: pila y árbol de activación.
4. `29_clases_herencia_clase.cps`: vtables y despacho dinámico.
5. `30_excepciones_clase.cps`: manejadores y restauración de estado.
6. `31_registros_clase.cps`: `getReg()` y derrames.

### Presentación corta, 8 a 10 minutos

1. `28_funciones_recursion_clase.cps`.
2. `29_clases_herencia_clase.cps`.
3. `30_excepciones_clase.cps`.
4. `31_registros_clase.cps`.

Las pruebas 26 y 27 pueden quedar preparadas como respaldo si solicitan variables, control de flujo o arreglos.

## 10. Validación antes de presentar

Ejecutar desde la raíz del repositorio:

```powershell
python .\verificar_proyecto.py
python .\verificar_mips.py --externo
python .\verificar_interfaz.py
```

Resultados de referencia:

```text
Proyecto completo: 197/197
Backend MIPS:       55/55
Interfaz real:      19/19
```

`verificar_mips.py --externo` usa MARS cuando encuentra Java y también SPIM si está instalado.

## 11. Cierre de la demostración

Al finalizar se puede resumir el flujo de esta forma:

1. El frontend valida el programa Compiscript.
2. El generador produce TAC.
3. El backend asigna registros y construye los marcos de activación.
4. El TAC se traduce a MIPS.
5. La mirilla elimina o reemplaza instrucciones redundantes.
6. El `.asm` incluye únicamente las rutinas y cadenas del runtime que necesita.
7. El mismo ensamblador se ejecuta en el simulador integrado y en MARS.

Para retirar la configuración temporal de UTF-8 al terminar:

```powershell
Remove-Item Env:PYTHONIOENCODING
```
