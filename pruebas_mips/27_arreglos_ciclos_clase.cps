// Arreglos, asignación por índice y recorrido con foreach.
let notas: integer[] = [70, 80, 90];
notas[0] = 75;

let suma: integer = 0;
foreach (nota in notas) {
  suma = suma + nota;
}

print(notas);
print(suma);
print(suma / 3);
