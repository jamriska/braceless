// Test mixing system headers with braceless headers
#include <vector>
#include <string>

#pragma once

#include <vector>
#include <string>

inline int sumVector(const std::vector<int>& v) {
    int sum = 0;
    for (const auto& x : v) {
        sum += x;
    }
    return sum;
}

inline int getLength(const std::string& s) {
    return static_cast<int>(s.length());
}

class StringWrapper {
private:
    std::string data;

public:
    StringWrapper(const std::string& s) : data(s) {}

    int length() const {
        return static_cast<int>(data.length());
    }

    const std::string& get() const {
        return data;
    }
};

int main() {
    std::vector<int> numbers;
    numbers.push_back(1);
    numbers.push_back(2);
    numbers.push_back(3);

    int sum = sumVector(numbers);

    std::string msg = "hello";
    int len = getLength(msg);

    StringWrapper sw("test");
    len += sw.length();

    return sum + len;
}
