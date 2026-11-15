# Publicar el Proyecto 3 en GitHub

## ¿Mismo repositorio o uno nuevo?

**El mismo repositorio, en una rama nueva.** El enunciado pide traducir el TAC del proyecto anterior a MIPS, así que el Proyecto 3 es la continuación del mismo código: reutiliza el frontend y el generador de TAC, y solo modifica unos pocos archivos de las fases anteriores (ver «Cambios respecto del Proyecto 2» en `README.md`). Una rama conserva la entrega del Proyecto 2 intacta en `main` y deja ver con claridad qué se agregó en esta fase.

Repositorio: `https://github.com/miafuentes30/PRY1-Compis.git`
Rama sugerida: `proyecto3-mips`

## Regla de la cátedra sobre commits

El enunciado indica que **se validan los commits de cada integrante y no se permite compartir commits**. Por eso este ZIP no trae historial de git: cada integrante debe subir, desde su propia cuenta, la parte que le corresponda y que pueda explicar. Repartan el trabajo según lo que realmente revisó y entiende cada persona; la tabla siguiente es solo una propuesta que separa el código en tres partes independientes.

| Integrante | Parte | Archivos |
| --- | --- | --- |
| 1 | Frontend para el backend y registros de activación | `semantic_analyzer.py`, `tac_ir.py`, `tac_generator.py`, `analyzer.py`, `analysis_result.py`, `mips_analysis.py`, `mips_frames.py`, `pruebas_semanticas/58_*`–`61_*` y su `manifest.json`, `pruebas_mips/12_*`, `13_*`, `14_*`, `19_*` |
| 2 | getReg, generación de código y runtime | `mips_ir.py`, `mips_regalloc.py`, `mips_codegen.py`, `mips_runtime.py`, `pruebas_mips/00_*`–`11_*`, `15_*`–`18_*`, `20_*`–`25_*`, `pruebas_mips/manifest.json` |
| 3 | Mirilla, simulador, IDE, consola, pruebas y documentación | `mips_peephole.py`, `mips_backend.py`, `mips_simulator.py`, `mips_external.py`, `herramientas/`, `main.py`, `compilar_cli.py`, `verificar_mips.py`, `verificar_proyecto.py`, `verificar_interfaz.py`, `*.md` |

## Pasos

### Integrante 1 (crea la rama)

```bash
git clone https://github.com/miafuentes30/PRY1-Compis.git
cd PRY1-Compis
git checkout -b proyecto3-mips
# copiar encima el contenido del ZIP (reemplazando archivos), luego:
git status                                  # revisar qué cambió
git add semantic_analyzer.py tac_ir.py tac_generator.py analyzer.py analysis_result.py \
        mips_analysis.py mips_frames.py pruebas_semanticas/
git add pruebas_mips/12_funciones_parametros.cps pruebas_mips/13_recursion.cps \
        pruebas_mips/14_closures.cps pruebas_mips/19_arbol_activacion.cps
git commit -m "P3: tipos en el TAC, análisis de flujo y registros de activación"
git push -u origin proyecto3-mips
```

Hasta que los demás suban su parte el programa no estará completo en la rama (por ejemplo, `analyzer.py` importa `mips_backend`); es normal en un trabajo por partes. Si prefieren que cada commit funcione por sí mismo, el integrante 3 puede subir primero `mips_backend.py`.

### Integrantes 2 y 3

```bash
git clone https://github.com/miafuentes30/PRY1-Compis.git   # o git fetch en un clon existente
cd PRY1-Compis
git checkout proyecto3-mips
git pull
# copiar SOLO los archivos de su parte desde el ZIP
git add <archivos de su parte>
git commit -m "P3: <descripción de su parte>"
git push
```

Cada quien debe usar su propio usuario (`git config user.name` y `git config user.email` de su cuenta de GitHub). Pueden hacer varios commits pequeños en lugar de uno grande, y cualquier corrección posterior debe hacerla quien la escriba.

### Al final

```bash
python verificar_proyecto.py      # debe dar 197/197 en la rama completa
```

Opcional: abrir un Pull Request de `proyecto3-mips` hacia `main` para la entrega, o entregar el enlace directo a la rama, según lo que indique el catedrático.

## Qué no subir

`__pycache__/`, `.venv/` y archivos `.asm`/`.tac` generados (el `.gitignore` ya excluye los dos primeros). Sí se suben `generated/` (lexer y parser de ANTLR) y `herramientas/Mars4_5.jar` con su licencia, para que el proyecto funcione sin instalar nada más que Python.
