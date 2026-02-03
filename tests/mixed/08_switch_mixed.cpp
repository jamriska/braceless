int main() {
    int x = 5;
    
    switch (x) {
        case 1:
            printf("One");
            break;
        case 2:
            if (x == 2) {
                printf("Two");
            }
            break;
        default:
            printf("Other");
    }
    
    return 0;
}
