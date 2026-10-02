class Animal {
  let x: integer;
  function constructor(x: integer) {
    this.x = x;
  }
}

class Dog : Animal {
  function value(): integer {
    return this.x;
  }
}

let d: Dog = new Dog(3);
print(d.value());
