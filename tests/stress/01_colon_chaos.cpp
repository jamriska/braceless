// Test multiple colon types in one construct
class ColonTest {
public:
    // Ternary with access specifier
    int getValue(int x) {
        return x > 0 ? x : -x;
    }
    
private:
    // Constructor initializer with ternary
    ColonTest(int a, int b) : value(a > b ? a : b), name("http://test") {
        initialize();
    }
    
    void initialize() {
        // Case with colon in string
        switch (value) {
            case 1:
                log("URL: http://example.com");
                break;
            default:
                log("Other: value");
        }
    }
    
    int value;
    const char* name;
};
