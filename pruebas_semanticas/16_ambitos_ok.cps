let x: integer = 1;
{
  let x: string = "local";
  print(x);
  { let y: string = x; print(y); }
}
print(x);
