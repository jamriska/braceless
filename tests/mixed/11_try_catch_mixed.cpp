int safe_divide(int a, int b) {
    try {
        if (b == 0) {
            throw std::runtime_error("Division by zero");
        }
        return a / b;
    } catch (std::exception& e) {
        return -1;
    }
}
