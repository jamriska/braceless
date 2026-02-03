void modifyPointer(int* ptr) {
    if (ptr != nullptr) {
        *ptr = 10;
    }
    
    while (ptr != nullptr && *ptr > 0) {
        (*ptr)--;
    }
}

int& getMax(int& a, int& b) {
    if (a > b) {
        return a;
    } else {
        return b;
    }
}
