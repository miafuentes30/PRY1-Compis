// Programa integrador: inventario con clases, herencia, arreglos, ciclos,
// recursión, switch y try/catch
class Producto {
  let nombre: string;
  let precio: integer;
  let cantidad: integer;

  function constructor(nombre: string, precio: integer, cantidad: integer) {
    this.nombre = nombre;
    this.precio = precio;
    this.cantidad = cantidad;
  }

  function total(): integer {
    return this.precio * this.cantidad;
  }

  function categoria(): string {
    return "general";
  }

  function resumen(): string {
    return this.nombre + " [" + this.categoria() + "] x" + this.cantidad + " = " + this.total();
  }
}

class Perecedero : Producto {
  let dias: integer = 3;

  function categoria(): string {
    return "perecedero";
  }

  function total(): integer {
    if (this.dias < 2) {
      return this.precio * this.cantidad / 2;
    }
    return this.precio * this.cantidad;
  }
}

function ordenar(datos: integer[], n: integer) {
  for (let i: integer = 0; i < n - 1; i = i + 1) {
    for (let j: integer = 0; j < n - 1 - i; j = j + 1) {
      if (datos[j] > datos[j + 1]) {
        let tmp: integer = datos[j];
        datos[j] = datos[j + 1];
        datos[j + 1] = tmp;
      }
    }
  }
}

function sumaRecursiva(datos: integer[], i: integer): integer {
  if (i < 0) {
    return 0;
  }
  return datos[i] + sumaRecursiva(datos, i - 1);
}

let leche: Perecedero = new Perecedero("Leche", 12, 10);
let inventario: Producto[] = [new Producto("Arroz", 8, 25), leche, new Producto("Frijol", 10, 30)];
leche.dias = 1;

let totales: integer[] = [0, 0, 0];
let k: integer = 0;
foreach (p in inventario) {
  print(p.resumen());
  totales[k] = p.total();
  k = k + 1;
}
ordenar(totales, 3);
print(totales);
print("Valor del inventario: " + sumaRecursiva(totales, 2));

let nivel: integer = sumaRecursiva(totales, 2) / 200;
switch (nivel) {
  case 0:
    print("inventario bajo");
    break;
  case 1:
    print("inventario medio");
    break;
  case 2:
    print("inventario alto");
    break;
  default:
    print("inventario excesivo");
}

try {
  print(inventario[5].resumen());
} catch (error) {
  print("No existe ese producto: " + error);
}
