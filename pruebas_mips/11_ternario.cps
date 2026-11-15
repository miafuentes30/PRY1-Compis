// Operador ternario
let x: integer = 7;
let tipo: string = x % 2 == 0 ? "par" : "impar";
print(tipo);
let mayor: integer = x > 10 ? x : 10;
print(mayor);
function absoluto(n: integer): integer {
  return n < 0 ? 0 - n : n;
}
print(absoluto(0 - 9));
print(absoluto(4));
let anidado: string = x < 5 ? "bajo" : (x < 10 ? "medio" : "alto");
print(anidado);
