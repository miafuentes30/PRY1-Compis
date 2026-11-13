// try / catch: errores en tiempo de ejecución capturados
let lista: integer[] = [1, 2, 3];

// índice fuera de rango
try {
  let peligro: integer = lista[100];
  print("no debe imprimirse");
} catch (err) {
  print("Error atrapado: " + err);
}

// división entre cero
let cero: integer = 0;
try {
  print(10 / cero);
} catch (e) {
  print("Error atrapado: " + e);
}

// referencia nula
class Caja {
  let valor: integer = 5;
  function leer(): integer { return this.valor; }
}
let caja: Caja = null;
try {
  print(caja.valor);
} catch (e) {
  print("Error atrapado: " + e);
}
try {
  print(caja.leer());
} catch (e) {
  print("Error atrapado: " + e);
}

// sin error: el catch no se ejecuta
try {
  print(lista[1]);
} catch (e) {
  print("no debe imprimirse");
}

// el error ocurre varias llamadas más abajo: se descartan los registros de activación
function profundo(n: integer): integer {
  if (n == 0) {
    return lista[0 - 1];
  }
  return profundo(n - 1) + 1;
}
try {
  print(profundo(4));
} catch (e) {
  print("Desde la recursion: " + e);
}

// try anidados y estado preservado después del catch
let estado: integer = 1;
try {
  estado = 2;
  try {
    estado = 3;
    print(lista[7]);
    estado = 4;
  } catch (interno) {
    print("interno: " + interno);
    estado = estado + 10;
  }
  print(10 % cero);
  estado = 99;
} catch (externo) {
  print("externo: " + externo);
}
print(estado);

// try dentro de un ciclo, con continue y break
let i: integer = 0;
let fallos: integer = 0;
while (i < 6) {
  i = i + 1;
  try {
    if (i == 2) {
      continue;
    }
    if (i == 5) {
      break;
    }
    print(lista[i]);
  } catch (e) {
    fallos = fallos + 1;
  }
}
print(fallos);
print(i);

// return dentro de try
function seguro(indice: integer): integer {
  try {
    return lista[indice];
  } catch (e) {
    return 0 - 1;
  }
}
print(seguro(2));
print(seguro(9));
try {
  print(seguro(1) + lista[5]);
} catch (e) {
  print("final: " + e);
}
print("fin");
