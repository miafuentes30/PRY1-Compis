// Presión de registros en una expresión corta.
let datos: integer[] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
let resultado: integer = datos[0] + (datos[1] + (datos[2] + (datos[3] +
  (datos[4] + (datos[5] + (datos[6] + (datos[7] + (datos[8] + datos[9]))))))));

print(resultado);
if (resultado == 55) {
  print("asignacion correcta");
}
