function obtener(): integer {
    try {
        return 1;
    } catch (error) {
        return 2;
    }
    print("Nunca se ejecuta");
}
