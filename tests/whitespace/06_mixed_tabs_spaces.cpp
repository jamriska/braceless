// Test mixing tabs and spaces in different blocks
void spaces_function() {
    int a = 1;
    if (a > 0) {
        do_something();
    }
}

void tabs_function() {
	int b = 2;
	if (b > 0) {
		do_other();
	}
}

class MixedClass {
    void method_spaces() {
        int x = 1;
    }
	void method_tabs() {
		int y = 2;
	}
};
