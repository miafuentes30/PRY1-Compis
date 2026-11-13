// Ciclo foreach sobre arreglos, con break y continue
let lista: integer[] = [3, 1, 4, 1, 5, 9, 2, 6];
let suma: integer = 0;
foreach (item in lista) {
  suma = suma + item;
}
print(suma);
foreach (n in lista) {
  if (n == 1) {
    continue;
  }
  if (n == 9) {
    break;
  }
  print(n);
}
let nombres: string[] = ["uno", "dos", "tres"];
foreach (texto in nombres) {
  print("-> " + texto);
}
let matriz: integer[][] = [[1, 2], [3, 4], [5, 6]];
let total: integer = 0;
foreach (fila in matriz) {
  foreach (celda in fila) {
    total = total + celda;
  }
}
print(total);
let vacio: integer[] = [];
foreach (nada in vacio) {
  print("no debe imprimirse");
}
print("fin");
