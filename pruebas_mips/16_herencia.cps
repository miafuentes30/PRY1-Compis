// Herencia: atributos y métodos heredados, sobrescritura y despacho dinámico
class Animal {
  let nombre: string;
  let patas: integer = 4;

  function constructor(nombre: string) {
    this.nombre = nombre;
  }

  function hablar(): string {
    return this.nombre + " hace ruido.";
  }

  function presentar(): string {
    return "Soy " + this.nombre + " y " + this.hablar();
  }

  function numeroPatas(): integer {
    return this.patas;
  }
}

class Perro : Animal {
  let trucos: integer = 2;

  function hablar(): string {
    return this.nombre + " ladra.";
  }

  function aprender(): integer {
    this.trucos = this.trucos + 1;
    return this.trucos;
  }
}

class Cachorro : Perro {
  function hablar(): string {
    return this.nombre + " chilla.";
  }
}

class Ave : Animal {
  function constructor(nombre: string) {
    this.nombre = nombre;
    this.patas = 2;
  }
}

let animal: Animal = new Animal("Generico");
let perro: Perro = new Perro("Toby");
let cachorro: Cachorro = new Cachorro("Bolt");
let ave: Ave = new Ave("Piolin");

print(animal.hablar());
print(perro.hablar());
print(cachorro.hablar());
print(ave.hablar());

// método heredado que invoca al método sobrescrito (despacho dinámico)
print(perro.presentar());
print(cachorro.presentar());

// atributos heredados e inicializadores de toda la jerarquía
print(perro.numeroPatas());
print(ave.numeroPatas());
print(cachorro.trucos);
print(cachorro.aprender());
print(perro.aprender());

// polimorfismo: variable de tipo base con objetos de clases derivadas
let mascota: Animal = perro;
print(mascota.hablar());
mascota = cachorro;
print(mascota.hablar());
function presentarAnimal(a: Animal): string {
  return a.presentar();
}
print(presentarAnimal(ave));
print(presentarAnimal(cachorro));
print(cachorro);
