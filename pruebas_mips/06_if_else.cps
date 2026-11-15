// Sentencia if / else, anidada y en cascada
let x: integer = 12;
if (x > 10) {
  print("Mayor a 10");
} else {
  print("Menor o igual");
}
if (x > 100) {
  print("no debe imprimirse");
}
if (x % 2 == 0) {
  if (x % 3 == 0) {
    print("divisible entre 6");
  } else {
    print("par");
  }
} else {
  print("impar");
}
function clasifica(n: integer): string {
  if (n < 0) {
    return "negativo";
  } else {
    if (n == 0) {
      return "cero";
    } else {
      if (n < 10) {
        return "pequeno";
      }
    }
  }
  return "grande";
}
print(clasifica(0 - 5));
print(clasifica(0));
print(clasifica(7));
print(clasifica(70));
let bandera: boolean = false;
if (!bandera) {
  print("bandera apagada");
}
