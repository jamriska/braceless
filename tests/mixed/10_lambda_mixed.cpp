int main() {
    auto lambda1 = [](int x) {
        return x * 2;
    };
    
    auto lambda2 = [](int x) {
        return x * 3;
    };
    
    int result = lambda1(5) + lambda2(10);
    return result;
}
