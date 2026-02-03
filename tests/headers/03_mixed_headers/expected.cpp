// Regular C++ header (not braceless)
#pragma once

struct RegularStruct {
    int value;
    
    RegularStruct() : value(0) {}
    RegularStruct(int v) : value(v) {}
    
    int getValue() const { return value; }
    void setValue(int v) { value = v; }
};

inline int regularFunction(int x) {
    return x * 2;
}

// Braceless header
#pragma once

class BracelessClass {
private:
    RegularStruct data;

public:
    BracelessClass() {}
    BracelessClass(int v) : data(v) {}

    int process() {
        int val = data.getValue();
        val = regularFunction(val);
        data.setValue(val);
        return val;
    }
};

int main() {
    RegularStruct rs(5);
    int x = regularFunction(rs.getValue());

    BracelessClass bc(10);
    int y = bc.process();

    return x + y;
}
