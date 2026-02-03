// Header with traditional include guard
#ifndef GUARDED_BLH
#define GUARDED_BLH

class GuardedClass {
private:
    int value;

public:
    GuardedClass() : value(0) {}
    GuardedClass(int v) : value(v) {}

    int getValue() const {
        return value;
    }

    void setValue(int v) {
        value = v;
    }
};

#endif // GUARDED_BLH

// First user of guarded header
#pragma once

class User1 {
private:
    GuardedClass obj;

public:
    int use() {
        obj.setValue(10);
        return obj.getValue();
    }
};

// Second user of guarded header
#pragma once

class User2 {
private:
    GuardedClass obj;

public:
    int use() {
        obj.setValue(20);
        return obj.getValue();
    }
};

// Both user1 and user2 include guarded.blh
// Include guard should prevent double definition

int main() {
    User1 u1;
    User2 u2;
    GuardedClass g(5);

    return u1.use() + u2.use() + g.getValue();
}
