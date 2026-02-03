// Test nested and complex continuations
class ContinuationStress {
public:
    // Multiline function parameters with continuation
    void complexParams(int first,
                      int second,
                      int third) : member(first + 
                                         second +
                                         third) {
        initialize();
    }
    
    // Nested function calls
    void nestedCalls() {
        result = outerFunc(innerFunc(a,
                                     b,
                                     c),
                          middleFunc(x +
                                    y +
                                    z),
                          finalFunc());
    }
    
    // Array with multiline initializer
    void arrays() {
        int data[] = {compute(1, 2),
                     compute(3, 4),
                     compute(5,
                            6,
                            7)};
    }
    
    // Chain of member access
    void chains() {
        value = object.getMember()
                     .getSubMember()
                     .process(arg1,
                             arg2)
                     .finalize();
    }
    
    // Continuation ending with colon (starts block)
    void continuationToBlock() {
        if (checkCondition(value1,
                         value2,
                         value3)) {
            action();
        }
    }
    
private:
    int member;
    int result;
    int value;
};
