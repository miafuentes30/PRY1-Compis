// Funciones anidadas (closures): acceso a variables de la función contenedora
// mediante el enlace de acceso del registro de activación
function crearContador(): integer {
  function siguiente(): integer {
    return 1;
  }
  return siguiente();
}
print(crearContador());

function acumular(inicio: integer): integer {
  let total: integer = inicio;
  function agregar(cantidad: integer): integer {
    total = total + cantidad;
    return total;
  }
  agregar(5);
  agregar(10);
  return agregar(1);
}
print(acumular(100));

// dos niveles de anidamiento: la más interna sigue dos enlaces de acceso
function nivel1(a: integer): integer {
  let x: integer = a * 2;
  function nivel2(b: integer): integer {
    let y: integer = b + x;
    function nivel3(c: integer): integer {
      x = x + 1;
      return a + x + y + c;
    }
    return nivel3(1) + nivel3(2);
  }
  let r: integer = nivel2(3);
  return r + x;
}
print(nivel1(5));

// función anidada recursiva que modifica una variable capturada
function contarLlamadas(n: integer): integer {
  let llamadas: integer = 0;
  function bajar(k: integer): integer {
    llamadas = llamadas + 1;
    if (k == 0) {
      return 0;
    }
    return bajar(k - 1);
  }
  bajar(n);
  return llamadas;
}
print(contarLlamadas(6));

// variable global modificada desde una función
let global: integer = 1;
function duplicarGlobal() {
  global = global * 2;
}
duplicarGlobal();
duplicarGlobal();
duplicarGlobal();
print(global);
