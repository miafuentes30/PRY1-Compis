function externa(a: integer): integer {
  let base: integer = a;
  function interna(b: integer): integer { return base + b; }
  return interna(2);
}
let r: integer = externa(3);
