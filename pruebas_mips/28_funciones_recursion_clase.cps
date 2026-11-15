// Funciones, parámetros, llamadas anidadas y recursividad.
function sumar(a: integer, b: integer): integer {
  return a + b;
}

function factorial(n: integer): integer {
  if (n <= 1) {
    return 1;
  }
  return n * factorial(n - 1);
}

function calcular(x: integer): integer {
  return sumar(factorial(x), 1);
}

print(sumar(3, 4));
print(factorial(5));
print(calcular(4));
