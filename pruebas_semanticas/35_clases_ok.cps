class Persona {
  let nombre: string;
  function constructor(nombre: string) { this.nombre = nombre; }
  function saludar(): string { return "Hola " + this.nombre; }
}
let p: Persona = new Persona("Ana");
let s: string = p.saludar();
