// Cadenas: concatenación, conversión implícita y comparación por contenido
let nombre: string = "Mundo";
let saludo: string = "Hola " + nombre;
print(saludo);
print(saludo + "!");
let edad: integer = 21;
print("Edad: " + edad);
print(edad + " años");
print("Negativo: " + (0 - 45));
print("Verdadero: " + true);
print("Suma: " + (2 + 3) + " y resta: " + (2 - 3));
let a: string = "abc";
let b: string = "ab" + "c";
print(a == b);
print(a != b);
print(a == "abd");
print("abc" < "abd");
print("b" > "abc");
print("abc" <= "abc");
print("" + 0);
let vacia: string;
print("Nulo: " + vacia);
if (a == b) {
  print("iguales por contenido");
}
if (a < "b") {
  print("abc va antes que b");
}
