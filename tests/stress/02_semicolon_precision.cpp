// Test edge cases for semicolon placement
class SemicolonTest {
private:
    // Lambda assignment
    std::function<int()> func = []() { return 42; };
    
    // Array initializer
    int arr[3] = {1, 2, 3};
    
public:
    // Constructor with inline body
    SemicolonTest() : func(nullptr) {}
    
    // Function returning lambda
    auto makeLambda() {
        return [](int x) { return x * 2; };
    }
    
    // Enum class
    enum class State {
        IDLE,
        RUNNING,
        DONE
    };
    
    // Function with ++ operator
    void increment(int& x) {
        x++;
        x--;
        ++x;
        --x;
    }
    
    // Closing brace contexts
    void complexBraces() {
        // Inline block
        if (true) { int x = 1; }
        
        // Array in statement
        int temp[] = {4, 5, 6};
        
        // Lambda call
        auto result = []() { return 99; }();
    }
};
