let a: integer[] = [1, 2, 3];
foreach (v in a) {
  if (v == 2) {
    continue;
  }
  if (v == 3) {
    break;
  }
  print(v);
}
