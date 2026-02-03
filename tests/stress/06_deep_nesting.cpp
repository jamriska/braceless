// Test deeply nested structures (10+ levels)
void deepNesting() {
    if (level1 > 0) {
        if (level2 > 0) {
            if (level3 > 0) {
                for (int i = 0; i < 10; i++) {
                    while (level5) {
                        switch (level6) {
                            case 1:
                                if (level7) {
                                    for (int j = 0; j < 5; j++) {
                                        if (level9) {
                                            while (level10) {
                                                if (level11) {
                                                    process();
                                                    level11--;
                                                }
                                                level10--;
                                            }
                                        }
                                        level9 = false;
                                    }
                                }
                                break;
                            default:
                                skip();
                        }
                        level5 = false;
                    }
                }
                level3--;
            }
        }
    }
}
