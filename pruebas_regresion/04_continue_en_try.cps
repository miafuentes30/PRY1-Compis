let i: integer = 0;
while (i < 3) {
    try { i = i + 1; continue; }
    catch (e) { print(e); }
}
