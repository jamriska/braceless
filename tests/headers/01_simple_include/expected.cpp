// Simple math utilities header
#pragma once

int add(int a, int b) {
    return a + b;
}

int multiply(int a, int b) {
    return a * b;
}

class Calculator {
public:
    int value;

    Calculator() : value(0) {}

    void add(int x) {
        value += x;
    }

    void subtract(int x) {
        value -= x;
    }

    int get() const {
        return value;
    }
};

int main() {
    int result = add(3, 4);
    result = multiply(result, 2);

    Calculator calc;
    calc.add(10);
    calc.subtract(3);

    return calc.get() + result;
}
