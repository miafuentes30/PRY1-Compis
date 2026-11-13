// switch / case: caída entre casos, break, default y discriminante string
function describe(x: integer) {
  switch (x) {
    case 1:
      print("uno");
    case 2:
      print("dos");
      break;
    case 3:
      print("tres");
      break;
    default:
      print("otro");
  }
}
describe(1);
describe(2);
describe(3);
describe(9);

let dia: string = "martes";
switch (dia) {
  case "lunes":
    print("inicio de semana");
    break;
  case "martes":
    print("segundo dia");
    break;
  default:
    print("otro dia");
}
let k: integer = 5;
switch (k * 2) {
  case 10:
    print("diez");
}
switch (k) {
  case 1:
    print("no");
}
print("fin");
