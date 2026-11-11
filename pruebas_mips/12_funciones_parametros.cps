// Funciones y parámetros: paso por registros ($a0-$a3) y por pila (5.º en adelante)
function suma(a: integer, b: integer): integer {
  return a + b;
}
function saludar(nombre: string): string {
  return "Hola " + nombre;
}
function sinRetorno(veces: integer) {
  let i: integer = 0;
  while (i < veces) {
    print("llamada " + i);
    i = i + 1;
  }
}
function seis(a: integer, b: integer, c: integer, d: integer, e: integer, f: integer): integer {
  return a * 100000 + b * 10000 + c * 1000 + d * 100 + e * 10 + f;
}
function promedio(datos: integer[], cantidad: integer): integer {
  let total: integer = 0;
  foreach (d in datos) {
    total = total + d;
  }
  return total / cantidad;
}
function esPar(n: integer): boolean {
  return n % 2 == 0;
}
function maximo(a: integer, b: integer): integer {
  if (a > b) {
    return a;
  }
  return b;
}

print(suma(2, 3));
let mensaje: string = saludar("Mundo");
print(mensaje);
sinRetorno(2);
print(seis(1, 2, 3, 4, 5, 6));
print(promedio([10, 20, 60], 3));
print(esPar(10));
print(esPar(7));
// llamadas anidadas y como argumentos
print(suma(suma(1, 2), suma(3, 4)));
print(maximo(suma(5, 5), maximo(3, 12)));
let x: integer = 4;
print(suma(x, x * 2) + suma(x, 1) * 2);
// los argumentos se evalúan de izquierda a derecha
print(seis(suma(0, 1), suma(1, 1), suma(1, 2), suma(2, 2), suma(2, 3), suma(3, 3)));
