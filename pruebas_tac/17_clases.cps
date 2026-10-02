class A {
  let x: integer = 1 + 2;

  function constructor(x: integer) {
    this.x = x;
  }

  function get(): integer {
    return this.x;
  }
}

let a: A = new A(4);
let x: integer = a.get();
