// try/catch y restauración de la pila cuando falla una función.
let valores: integer[] = [10, 20];

function leer(indice: integer): integer {
  return valores[indice];
}

try {
  print(leer(5));
} catch (error) {
  print("capturado: " + error);
}

print("el programa continua");
