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
