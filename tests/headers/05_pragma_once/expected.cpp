// Shared header with pragma once
#pragma once

constexpr int SHARED_CONSTANT = 42;

inline int sharedFunction(int x) {
    return x + SHARED_CONSTANT;
}

#pragma once

class ModuleA {
public:
    int compute(int x) {
        return sharedFunction(x) * 2;
    }
};

#pragma once

class ModuleB {
public:
    int compute(int x) {
        return sharedFunction(x) + SHARED_CONSTANT;
    }
};

int main() {
    ModuleA a;
    ModuleB b;

    int result = a.compute(10) + b.compute(10);
    result += sharedFunction(5);

    return result;
}
