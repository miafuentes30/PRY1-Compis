class Animal {
  let nombre: string;
  function constructor(nombre: string) { this.nombre = nombre; }
  function hablar(): string { return this.nombre; }
}
class Perro : Animal {
  function ladrar(): string { return this.nombre + " ladra"; }
}
let p: Perro = new Perro("Toby");
let s: string = p.ladrar();
