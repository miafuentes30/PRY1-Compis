// Caso fallido en la generación de código: una clase declarada dentro de una
// función intenta leer una variable local de esa función. El enlace de acceso
// solo existe para funciones anidadas, así que el backend lo rechaza con un
// diagnóstico en lugar de producir código incorrecto.
function fabrica(base: integer): integer {
  class Interna {
    function valor(): integer {
      return base;
    }
  }
  let obj: Interna = new Interna();
  return obj.valor();
}
print(fabrica(3));
