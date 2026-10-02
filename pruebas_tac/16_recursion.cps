function fact(n: integer): integer {
  if (n <= 1) {
    return 1;
  } else {
    return n * fact(n - 1);
  }
}

let result: integer = fact(5);
