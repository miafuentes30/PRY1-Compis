// Recursividad: cada llamada crea su propio registro de activación
function factorial(n: integer): integer {
  if (n <= 1) {
    return 1;
  }
  return n * factorial(n - 1);
}
function fibonacci(n: integer): integer {
  if (n < 2) {
    return n;
  }
  return fibonacci(n - 1) + fibonacci(n - 2);
}
function potencia(base: integer, exponente: integer): integer {
  if (exponente == 0) {
    return 1;
  }
  return base * potencia(base, exponente - 1);
}
function mcd(a: integer, b: integer): integer {
  if (b == 0) {
    return a;
  }
  return mcd(b, a % b);
}
function sumaDigitos(n: integer): integer {
  if (n < 10) {
    return n;
  }
  return n % 10 + sumaDigitos(n / 10);
}
// recursión mutua
function esPar(n: integer): boolean {
  if (n == 0) {
    return true;
  }
  return esImpar(n - 1);
}
function esImpar(n: integer): boolean {
  if (n == 0) {
    return false;
  }
  return esPar(n - 1);
}
function hanoi(discos: integer, origen: string, destino: string, auxiliar: string): integer {
  if (discos == 0) {
    return 0;
  }
  let antes: integer = hanoi(discos - 1, origen, auxiliar, destino);
  let despues: integer = hanoi(discos - 1, auxiliar, destino, origen);
  return antes + 1 + despues;
}
function ackermann(m: integer, n: integer): integer {
  if (m == 0) {
    return n + 1;
  }
  if (n == 0) {
    return ackermann(m - 1, 1);
  }
  return ackermann(m - 1, ackermann(m, n - 1));
}

print(factorial(5));
print(factorial(10));
print(fibonacci(10));
print(potencia(2, 10));
print(mcd(48, 36));
print(sumaDigitos(98765));
print(esPar(10));
print(esImpar(7));
print(hanoi(5, "A", "C", "B"));
print(ackermann(2, 3));
