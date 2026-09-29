// Debe retirarse el manejador antes de retornar.
function f(): integer {
    try { return 1; }
    catch (e) { return 0; }
}
let valor: integer = f();
