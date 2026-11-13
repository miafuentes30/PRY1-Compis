// Caso fallido en tiempo de ejecución: división entre cero sin manejar
function dividir(a: integer, b: integer): integer {
  return a / b;
}
print(dividir(10, 2));
print(dividir(1, 0));
print("no debe imprimirse");
