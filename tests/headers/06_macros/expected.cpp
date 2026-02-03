// Header with macros
#pragma once

#define MAX_VALUE 100
#define MIN_VALUE 0

#define CLAMP(x, lo, hi) ((x) < (lo) ? (lo) : ((x) > (hi) ? (hi) : (x)))

#ifdef DEBUG
#define LOG(msg) print_debug(msg)
#else
#define LOG(msg)
#endif

inline int clampValue(int x) {
    return CLAMP(x, MIN_VALUE, MAX_VALUE);
}

class Bounded {
private:
    int value;

public:
    Bounded() : value(MIN_VALUE) {}

    void set(int v) {
        value = CLAMP(v, MIN_VALUE, MAX_VALUE);
    }

    int get() const {
        return value;
    }
};

int main() {
    int x = clampValue(150);
    int y = clampValue(-10);

    Bounded b;
    b.set(50);
    int z = b.get();

    LOG("test message");

    return x + y + z;
}
