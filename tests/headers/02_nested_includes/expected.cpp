// Base types header
#pragma once

struct Point {
    int x;
    int y;

    Point() : x(0), y(0) {}
    Point(int x, int y) : x(x), y(y) {}
};

struct Size {
    int width;
    int height;

    Size() : width(0), height(0) {}
    Size(int w, int h) : width(w), height(h) {}
};

// Geometry header - includes base_types.blh
#pragma once

class Rectangle {
private:
    Point origin;
    Size size;

public:
    Rectangle() {}
    Rectangle(Point o, Size s) : origin(o), size(s) {}

    int area() const {
        return size.width * size.height;
    }

    bool contains(Point p) const {
        return p.x >= origin.x &&
               p.x < origin.x + size.width &&
               p.y >= origin.y &&
               p.y < origin.y + size.height;
    }

    Point getCenter() const {
        Point center;
        center.x = origin.x + size.width / 2;
        center.y = origin.y + size.height / 2;
        return center;
    }
};

int main() {
    Point p(10, 20);
    Size s(100, 50);
    Rectangle rect(p, s);

    int a = rect.area();

    Point test(50, 40);
    if (rect.contains(test)) {
        a += 1;
    }

    Point center = rect.getCenter();
    return center.x + center.y + a;
}
