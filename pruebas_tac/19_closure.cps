function outer(x:integer):integer {function inner():integer{return x+1;} return inner();} let v:integer=outer(3);
