// Expresiones lógicas y relacionales, con evaluación en cortocircuito
let contador: integer = 0;
function marca(valor: boolean): boolean {
  contador = contador + 1;
  return valor;
}
let x: integer = 15;
let y: boolean = !(x < 10 || x > 20);
print(y);
print(x > 10 && x < 20);
print(x == 15);
print(x != 15);
print(x <= 15);
print(x >= 16);
print(true && false);
print(true || false);
print(!true);
print(!false || false);

// && no evalúa el segundo operando si el primero es falso
let p: boolean = marca(false) && marca(true);
print(p);
print(contador);
// || no evalúa el segundo operando si el primero es verdadero
let q: boolean = marca(true) || marca(false);
print(q);
print(contador);
// ambos operandos se evalúan cuando es necesario
let s: boolean = marca(true) && marca(true);
print(s);
print(contador);
let t: boolean = (x > 5 && x < 10) || (x > 12 && !(x == 13));
print(t);
