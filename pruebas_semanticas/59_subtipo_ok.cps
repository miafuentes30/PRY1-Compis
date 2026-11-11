// Proyecto 3: una instancia derivada puede usarse donde se espera la clase base.
class Animal { function hablar(): string { return "..."; } }
class Perro : Animal { function hablar(): string { return "guau"; } }
let a: Animal = new Perro();
function oir(x: Animal): string { return x.hablar(); }
print(oir(new Perro()));
let lista: Animal[] = [new Animal(), new Perro()];
