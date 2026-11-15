// Árbol de activación: cada llamada crea un nodo con sus argumentos y su resultado
function fib(n: integer): integer {
  if (n < 2) {
    return n;
  }
  return fib(n - 1) + fib(n - 2);
}
function doble(x: integer): integer {
  return x * 2;
}
function compuesto(x: integer): integer {
  return doble(x) + doble(x + 1);
}
print(fib(4));
print(compuesto(3));
