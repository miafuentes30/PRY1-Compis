while (true) {
    try {
        try { break; }
        catch (inner) { print(inner); }
    } catch (outer) { print(outer); }
}
