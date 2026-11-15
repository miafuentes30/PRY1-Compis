// Arreglos de una y dos dimensiones
let notas: integer[] = [90, 85, 100];
print(notas[0]);
print(notas[2]);
notas[1] = notas[0] + 5;
print(notas[1]);
print(notas);

let matriz: integer[][] = [[1, 2, 3], [4, 5, 6]];
print(matriz[1][2]);
matriz[0][0] = matriz[1][1] * 10;
print(matriz[0][0]);
print(matriz);

let nombres: string[] = ["Ana", "Luis", "Eva"];
print(nombres[1]);
print(nombres);
let banderas: boolean[] = [true, false];
print(banderas);

let i: integer = 0;
let suma: integer = 0;
while (i < 3) {
  suma = suma + notas[i];
  i = i + 1;
}
print(suma);

let vacio: integer[] = [];
print(vacio);
let indice: integer = 2;
notas[indice] = notas[indice - 1] - notas[indice - 2];
print(notas[indice]);
function ultimo(datos: integer[], cantidad: integer): integer {
  return datos[cantidad - 1];
}
print(ultimo(notas, 3));
