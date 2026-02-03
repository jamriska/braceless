#include <cstring>

bool isEmpty(const char* str) {
    return str == nullptr || strlen(str) == 0;
}

int processString(const char* str) {
    // Function calls in condition without parens
    if (isEmpty(str)) {
        return 0;
    }
    
    int count = 0;
    while (!isEmpty(str) && count < 10) {
        count++;
    }
    
    for (int i = 0; i < strlen(str); i++) {
        if (str[i] == 'a') {
            count++;
        }
    }
    
    return count;
}
