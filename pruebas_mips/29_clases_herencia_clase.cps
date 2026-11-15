// Clases, objetos, constructor, herencia y despacho dinámico.
class Animal {
  let nombre: string;

  function constructor(nombre: string) {
    this.nombre = nombre;
  }

  function hablar(): string {
    return this.nombre + " hace ruido";
  }

  function presentar(): string {
    return "Soy " + this.nombre + ": " + this.hablar();
  }
}

class Perro : Animal {
  function hablar(): string {
    return this.nombre + " ladra";
  }
}

let mascota: Animal = new Perro("Luna");
print(mascota.nombre);
print(mascota.presentar());
