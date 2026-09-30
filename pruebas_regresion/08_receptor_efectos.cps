class A {
    let x: integer = 1;
    function get(v: integer): integer { return this.x; }
}
let a: A = new A();
function change(): integer { a = new A(); return 2; }
let y: integer = a.get(change());
