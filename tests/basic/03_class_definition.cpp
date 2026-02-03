class Point {
    int x;
    int y;
    
    Point(int x, int y) {
        this->x = x;
        this->y = y;
    }
    
    int distance() {
        return x * x + y * y;
    }
};
