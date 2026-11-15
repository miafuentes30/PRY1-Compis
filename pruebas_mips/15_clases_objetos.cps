// Clases y objetos: atributos, constructor, métodos, this e inicializadores
class Punto {
  let x: integer;
  let y: integer;
  let etiqueta: string = "punto";
  const dimension: integer = 2;

  function constructor(x: integer, y: integer) {
    this.x = x;
    this.y = y;
  }

  function mover(dx: integer, dy: integer) {
    this.x = this.x + dx;
    this.y = this.y + dy;
  }

  function sumaCoordenadas(): integer {
    return this.x + this.y;
  }

  function describir(): string {
    return this.etiqueta + " (" + this.x + ", " + this.y + ")";
  }
}

class Contador {
  let cuenta: integer = 0;
  let paso: integer = 3;

  function incrementar(): integer {
    cuenta = cuenta + paso;
    return cuenta;
  }

  function dosVeces(): integer {
    incrementar();
    return incrementar();
  }
}

let p: Punto = new Punto(3, 4);
print(p.x);
print(p.y);
print(p.sumaCoordenadas());
p.mover(10, 20);
print(p.describir());
p.x = 100;
print(p.x);
print(p.etiqueta);
print(p.dimension);
print(p);

let q: Punto = new Punto(1, 1);
q.mover(1, 1);
print(q.describir());
print(p.describir());

let c: Contador = new Contador();
print(c.incrementar());
print(c.dosVeces());
print(c.cuenta);

// objetos dentro de arreglos y como parámetros
let puntos: Punto[] = [new Punto(1, 2), new Punto(3, 4), new Punto(5, 6)];
let total: integer = 0;
foreach (punto in puntos) {
  total = total + punto.sumaCoordenadas();
}
print(total);
function distanciaManhattan(a: Punto, b: Punto): integer {
  let dx: integer = a.x - b.x;
  let dy: integer = a.y - b.y;
  if (dx < 0) { dx = 0 - dx; }
  if (dy < 0) { dy = 0 - dy; }
  return dx + dy;
}
print(distanciaManhattan(puntos[0], puntos[2]));
print(puntos[1].describir());
