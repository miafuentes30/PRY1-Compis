// Ciclos while y do-while, con break y continue
let x: integer = 0;
while (x < 5) {
  x = x + 1;
}
print(x);
do {
  x = x - 2;
} while (x > 0);
print(x);

// do-while ejecuta el cuerpo al menos una vez
let veces: integer = 0;
do {
  veces = veces + 1;
} while (false);
print(veces);

let n: integer = 0;
let suma: integer = 0;
while (true) {
  n = n + 1;
  if (n > 10) {
    break;
  }
  if (n % 2 == 0) {
    continue;
  }
  suma = suma + n;
}
print(suma);

// ciclos anidados
let i: integer = 1;
let total: integer = 0;
while (i <= 3) {
  let j: integer = 1;
  while (j <= i) {
    total = total + i * j;
    j = j + 1;
  }
  i = i + 1;
}
print(total);
