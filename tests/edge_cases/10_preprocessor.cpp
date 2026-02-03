#include <stdio.h>
#define MAX 100

int main() {
    #ifdef DEBUG
    printf("Debug mode");
    #endif
    return 0;
}
