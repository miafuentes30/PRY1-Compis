// Ciclo for: completo, sin condición, con break y continue, anidado
for (let i: integer = 0; i < 3; i = i + 1) {
  print(i);
}
let suma: integer = 0;
for (let k: integer = 1; k <= 100; k = k + 1) {
  suma = suma + k;
}
print(suma);
let pares: integer = 0;
for (let k: integer = 0; k < 10; k = k + 1) {
  if (k % 2 == 1) {
    continue;
  }
  pares = pares + 1;
}
print(pares);
let j: integer = 0;
for (; ; j = j + 1) {
  if (j == 4) {
    break;
  }
}
print(j);
let celdas: integer = 0;
for (let f: integer = 0; f < 4; f = f + 1) {
  for (let c: integer = 0; c < 5; c = c + 1) {
    if (c > f) {
      break;
    }
    celdas = celdas + 1;
  }
}
print(celdas);
let cuenta: integer = 10;
for (cuenta = 3; cuenta > 0; cuenta = cuenta - 1) {
  print("faltan " + cuenta);
}
