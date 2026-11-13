// Caso fallido en compilación: errores semánticos. No se genera TAC ni MIPS.
let x: integer = "texto";
function f(a: integer): integer {
  return a + true;
}
print(f(1, 2));
