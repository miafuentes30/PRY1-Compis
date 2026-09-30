// Evaluar change() ANTES de inicializar los atributos de A.
let a: integer = 1;
function change(): integer { a = 5; return a; }
class A {
    let x: integer = a;
    function constructor(v: integer) { this.x = v; }
}
let obj: A = new A(change());
