// Test multiline optional parentheses in complex scenarios
void multilineStress(int a, int b, int c) {
    // Multiline if with function calls
    if (someFunc(a) > 0 &&
       otherFunc(b) < 10 &&
       thirdFunc(c) != 0) {
        process();
    }
    
    // Nested multiline controls
    for (int i = 0; 
        i < count &&
        i < MAX; 
        i++) {
        if (data[i] > threshold &&
           data[i] < limit) {
            handle(data[i]);
        }
    }
    
    // While with complex condition
    while (isValid() &&
          !isDone() &&
          hasMore()) {
        step();
    }
    
    // Multiline with operators at different indents
    if ((calculateValue(a, b) > MIN_VALUE) &&
                    checkCondition(c) &&
       finalValidation()) {
        execute();
    }
    
    // For with multiline init/condition/increment
    for (int x = initialize(a, 
                          b,
                          c);
        x < getMax() && 
        x > getMin();
        x += getStep()) {
        work(x);
    }
}
