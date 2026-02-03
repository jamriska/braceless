// Test deeply nested tab indentation
void nested() {
	if (true) {
		for (int i = 0; i < 10; i++) {
			while (running) {
				switch (state) {
					case 1:
						handle_one();
						break;
					default:
						handle_default();
				}
			}
		}
	}
}
