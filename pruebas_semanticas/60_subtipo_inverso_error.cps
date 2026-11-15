// Una instancia de la clase base NO puede asignarse a una variable de la clase derivada.
class Animal { let n: integer = 1; }
class Perro : Animal { let m: integer = 2; }
let p: Perro = new Animal();
