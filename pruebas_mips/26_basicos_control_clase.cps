// Variables, constantes, aritmética, lógica, if/else y for.
const BONO: integer = 5;
let base: integer = 10;
let total: integer = base * 2 + BONO;
let enRango: boolean = total >= 20 && total < 30;

print(total);
if (enRango) {
  print("dentro del rango");
} else {
  print("fuera del rango");
}

for (let i: integer = 1; i <= 3; i = i + 1) {
  print(i);
}
