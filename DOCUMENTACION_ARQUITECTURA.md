# Arquitectura del compilador de Compiscript — Proyecto 3

El compilador completo traduce un archivo `.cps` a ensamblador MIPS32 y lo ejecuta en un simulador. Se construyó por fases sobre el mismo repositorio: el Proyecto 1 aportó el análisis léxico, sintáctico y semántico; el Proyecto 2, el código intermedio (TAC); el Proyecto 3 añade el backend MIPS, la optimización por mirilla, el simulador y las pestañas nuevas del IDE. Los documentos de arquitectura de las fases anteriores se conservan en `DOCUMENTACION_ARQUITECTURA_PROYECTO1.md` y `DOCUMENTACION_ARQUITECTURA_PROYECTO2.md`.

## 1. Pipeline

```text
                IDE Tkinter (main.py)  ·  consola (compilar_cli.py)
                               │  texto fuente .cps
                               ▼
 ┌──────────────────────── FRONTEND (P1) ─────────────────────────┐
 │ ANTLR Lexer ─► Parser ─► árbol sintáctico                       │
 │ SpanishErrorListener · recuperación de errores                  │
 │ SemanticAnalyzer (Visitor): tipos, ámbitos, clases, herencia    │
 │ SymbolTable: ámbitos, símbolos, plan de almacenamiento          │
 └────────────── si hay errores: diagnósticos, sin TAC ni MIPS ───┘
                               │
                               ▼
 ┌─────────────────── CÓDIGO INTERMEDIO (P2) ─────────────────────┐
 │ TACGenerator (Visitor) ─► TACProgram (instrucciones tipadas)    │
 │ TemporaryPool por función · etiquetas · manejadores try         │
 └─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
 ┌────────────────────────── BACKEND (P3) ─────────────────────────┐
 │ mips_analysis   bloques básicos, flujo, vida de variables       │
 │ mips_frames     registros de activación, enlaces, vtables       │
 │ mips_regalloc   getReg(): descriptores, derrames                │
 │ mips_codegen    traducción TAC → MIPS, llamadas y retornos      │
 │ mips_runtime    biblioteca MIPS (print, cadenas, excepciones…)  │
 │ mips_peephole   optimización por mirilla (11 reglas)            │
 └────────────── si falla: diagnóstico MIPS_UNSUPPORTED ──────────┘
                               │  .asm
                ┌──────────────┴───────────────┐
                ▼                              ▼
     mips_simulator (integrado)       mips_external: MARS 4.5 / SPIM
     salida + árbol de activación     (misma salida, verificado)
```

`CompiscriptAnalyzer.analyze_full_text()` (en `analyzer.py`) orquesta todas las fases y devuelve un `FullAnalysisResult` con diagnósticos, árbol, tabla de símbolos, TAC y `mips` (un `MIPSResult`). Ninguna fase produce salida parcial: si una falla, las posteriores no se ejecutan y el IDE limpia las vistas correspondientes.

## 2. Módulos

| Módulo | Fase | Responsabilidad |
| --- | --- | --- |
| `Compiscript.g4`, `generated/` | P1 | Gramática oficial y lexer/parser/visitor de ANTLR 4.9.3 (incluidos; no hace falta Java para usarlos). |
| `error_listener.py`, `reserved_word_diagnostics.py` | P1 | Diagnósticos léxicos y sintácticos en español, con sugerencias. |
| `semantic_analyzer.py` | P1, P3 | Reglas semánticas; desde P3 anota el tipo de cada expresión, acepta subtipos y la concatenación con conversión. |
| `symbol_table.py` | P1, P2 | Ámbitos, símbolos y plan abstracto de almacenamiento. |
| `tac_ir.py`, `tac_generator.py` | P2, P3 | IR de tres direcciones; desde P3 lleva tipos por instrucción y metadatos de funciones. |
| `analyzer.py`, `analysis_result.py` | todas | Pipeline completo y resultado. |
| `mips_analysis.py` | P3 | Unidades, bloques básicos, CFG con aristas excepcionales, variables vivas, siguiente uso. |
| `mips_frames.py` | P3 | Registros de activación, registros `$s` por función, enlaces de acceso, diseño de objetos y vtables. |
| `mips_regalloc.py` | P3 | `getReg()` con descriptores de registro y dirección, derrames, guardado caller-saved. |
| `mips_codegen.py` | P3 | Traducción de cada instrucción TAC, prólogos, epílogos y secuencias de llamada. |
| `mips_runtime.py` | P3 | Rutinas MIPS de soporte (impresión, cadenas, arreglos, objetos, excepciones). |
| `mips_peephole.py` | P3 | Optimización por mirilla con reporte de cambios. |
| `mips_ir.py`, `mips_backend.py` | P3 | Representación del ensamblador y fachada `compile_tac()` / `MIPSResult`. |
| `mips_simulator.py` | P3 | Simulador MIPS integrado y árbol de activación. |
| `mips_external.py` | P3 | Ejecución en MARS (`herramientas/Mars4_5.jar`) y SPIM. |
| `main.py` | todas | IDE: editor, diagnósticos, TAC, MIPS, ejecución, activación, registros, mirilla, símbolos y árbol ANTLR. |
| `compilar_cli.py` | todas | Compilador de consola (TAC, `.asm`, ejecución, árbol, reportes, MARS/SPIM). |
| `verificar_*.py` | todas | Baterías automatizadas. |

## 3. Decisiones de diseño del backend

1. **Trabajar sobre el TAC, no sobre el árbol.** El backend solo conoce instrucciones TAC; por eso el TAC se enriqueció con tipos estáticos en lugar de repetir el análisis semántico.
2. **Dos niveles de asignación de registros.** Las variables de cada función se asignan de forma global a `$s0`–`$s7` (sobreviven a llamadas sin guardarse en cada una); los temporales usan `getReg()` local por bloque sobre `$t0`–`$t7`. Así las llamadas solo guardan los temporales realmente vivos.
3. **Análisis de vida con aristas excepcionales.** Un `catch` puede alcanzarse desde cualquier operación que falle dentro del `try`; esas aristas se agregan al grafo para que nada que el manejador necesite quede solo en un registro.
4. **Vtables para herencia.** Los métodos sobrescritos ocupan la misma posición que en la clase base; los campos heredados van primero. El despacho es `lw` + `lw` + `jalr`.
5. **Enlaces de acceso para funciones anidadas** (la gramática permite funciones dentro de funciones y el README las llama *closures*).
6. **Runtime en MIPS, no en el simulador.** Todo (concatenación, conversión de enteros, impresión de arreglos, excepciones) está escrito en MIPS dentro del `.asm`, por eso el mismo archivo corre en MARS, SPIM y QtSpim.
7. **Simulador propio para el IDE.** Permite ejecutar sin instalar Java y, sobre todo, observar llamadas y retornos para construir el árbol de activación. Su fidelidad se comprueba contra MARS y SPIM reales.
8. **Mirilla como pasada independiente** sobre el ensamblador estructurado; cada cambio queda registrado y la batería compara la salida con y sin optimización.

## 4. Manejo de errores por fase

| Fase | Resultado ante un error |
| --- | --- |
| Léxica / sintáctica | Diagnósticos; no se ejecuta el análisis semántico para evitar cascadas. |
| Semántica | Todos los diagnósticos del archivo; sin TAC ni MIPS. |
| TAC | `TAC_UNSUPPORTED` y se descarta el TAC parcial. |
| MIPS | `MIPS_UNSUPPORTED` (tipo «Generación»); se conserva el TAC, sin `.asm`. |
| Ejecución | Errores atrapables (índice, división entre cero, nulo) van al `catch`; sin `try`, mensaje y código de salida 1. El simulador además detecta desbordamiento de pila, ciclos sin fin (límite de instrucciones) y saltos inválidos. |

## 5. Verificación

| Script | Qué verifica |
| --- | --- |
| `python verificar_proyecto.py` | 197 verificaciones: semántica (61), recuperación (3), tabla de símbolos (4), TAC (30), invariantes (4), regresiones (40) y MIPS (55). |
| `python verificar_mips.py [--externo]` | Solo el Proyecto 3; con `--externo` compara cada programa contra MARS y SPIM. |
| `python verificar_interfaz.py` | 19 comprobaciones del IDE real (requiere pantalla o `xvfb-run`). |

Los detalles del backend (marcos, `getReg`, traducciones, runtime, try/catch, mirilla y simulador) están en `DOCUMENTACION_MIPS.md`.
