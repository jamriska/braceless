// Test special constructs combined in complex ways
class SpecialStress {
private:
    // Lambda in constructor initializer
    SpecialStress(int x) : callback([](int v) { return v * 2; }),
                          value(x > 0 ? x : -x) {
        initialize();
    }
    
    // Nested enum class with complex values
    enum class Status {
        INIT = (1 << 0),
        READY = (1 << 1) | (1 << 2),
        DONE = STATUS_MAX - 1
    };
    
    // Union with nested struct
    union Data {
        int intVal;
        struct Details {
            short a;
            short b;
        };
    };
    
    // do-while with else after
    void doWhileElse(int& x) {
        do {
            x++;
        } while (x < 10);
        
        if (x >= 10) {
            reset(x);
        } else {
            continue_processing();
        }
    }
    
public:
    // Lambda returning lambda
    auto makeLambda() {
        return [](int x) {
                   return [x](int y) { return x + y; };
               };
    }
    
    // Template function with optional parens
    template<typename T>
    void process(T value) {
        if (sizeof(T) > 4) {
            handleLarge(value);
        } else {
            handleSmall(value);
        }
    }
    
    // Try-catch with optional parens
    void tryCatch() {
        try {
            if (risky()) {
                throw std::runtime_error("error");
            }
        } catch (const std::exception& e) {
            log(e.what());
        }
    }
    
private:
    std::function<int(int)> callback;
    int value;
};
