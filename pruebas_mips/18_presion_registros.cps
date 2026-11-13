// Asignación de registros bajo presión: más valores vivos que registros $t y $s,
// lo que obliga a getReg() a derramar (spill) en el registro de activación
function muchos(a: integer, b: integer, c: integer, d: integer, e: integer,
                f: integer, g: integer, h: integer, i: integer, j: integer): integer {
  let k: integer = a + b;
  let l: integer = c + d;
  let m: integer = e + f;
  let n: integer = g + h;
  let o: integer = i + j;
  return (a + (b + (c + (d + (e + (f + (g + (h + (i + (j + (k + (l + (m + (n + o))))))))))))))
       * ((a * b) + (c * d) + (e * f) + (g * h) + (i * j)) % 1000;
}
print(muchos(1, 2, 3, 4, 5, 6, 7, 8, 9, 10));

let v1: integer = 1;
let v2: integer = 2;
let v3: integer = 3;
let v4: integer = 4;
let v5: integer = 5;
let v6: integer = 6;
let v7: integer = 7;
let v8: integer = 8;
let v9: integer = 9;
let v10: integer = 10;
let v11: integer = 11;
let v12: integer = 12;
// expresión cargada a la derecha: muchos resultados parciales vivos a la vez
let profundo: integer = v1 * (v2 + v3 * (v4 - v5 * (v6 + v7 * (v8 - v9 * (v10 + v11 * (v12 - v1 * (v2 + v3 * (v4 - v5))))))));
print(profundo);
let suma: integer = v1 + v2 + v3 + v4 + v5 + v6 + v7 + v8 + v9 + v10 + v11 + v12;
print(suma);
// temporales vivos a través de llamadas (se guardan antes del jal)
function id(x: integer): integer { return x; }
print(id(v1) + id(v2) * (id(v3) + id(v4) * (id(v5) + id(v6) * (id(v7) + id(v8)))));
// cada elemento leído es un temporal distinto y todos siguen vivos hasta el final:
// se necesitan más de 8 registros $t y getReg() elige víctimas para derramar
let a: integer[] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
print(a[0] * (a[1] + a[2] * (a[3] - a[4] * (a[5] + a[6] * (a[7] - a[8] * (a[9] + a[10] * a[11]))))));
print(a[0] + (a[1] + (a[2] + (a[3] + (a[4] + (a[5] + (a[6] + (a[7] + (a[8] + (a[9] + (a[10] + a[11])))))))))));
