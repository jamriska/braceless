#include <string>
#include <map>
#include <vector>
#include <memory>
#include <stdexcept>

enum JsonType {
    NULL_TYPE,
    BOOL_TYPE,
    NUMBER_TYPE,
    STRING_TYPE,
    ARRAY_TYPE,
    OBJECT_TYPE
};

class JsonValue {
private:
    JsonType type;
    union Data {
        bool boolVal;
        double numberVal;
        std::string* stringVal;
        std::vector<JsonValue>* arrayVal;
        std::map<std::string, JsonValue>* objectVal;
    };
    
    Data data;
    
public:
    JsonValue() : type(NULL_TYPE) {}
    
    explicit JsonValue(bool value) : type(BOOL_TYPE) {
        data.boolVal = value;
    }
    
    explicit JsonValue(double value) : type(NUMBER_TYPE) {
        data.numberVal = value;
    }
    
    explicit JsonValue(const std::string& value) : type(STRING_TYPE) {
        data.stringVal = new std::string(value);
    }
    
    ~JsonValue() {
        if (type == STRING_TYPE) {
            delete data.stringVal;
        } else if (type == ARRAY_TYPE) {
            delete data.arrayVal;
        } else if (type == OBJECT_TYPE) {
            delete data.objectVal;
        }
    }
    
    JsonType getType() const {
        return type;
    }
    
    bool isNull() const { return type == NULL_TYPE; }
    bool isBool() const { return type == BOOL_TYPE; }
    bool isNumber() const { return type == NUMBER_TYPE; }
    bool isString() const { return type == STRING_TYPE; }
    bool isArray() const { return type == ARRAY_TYPE; }
    bool isObject() const { return type == OBJECT_TYPE; }
    
    bool asBool() const {
        if (type != BOOL_TYPE) {
            throw std::runtime_error("Not a boolean");
        }
        return data.boolVal;
    }
    
    double asNumber() const {
        if (type != NUMBER_TYPE) {
            throw std::runtime_error("Not a number");
        }
        return data.numberVal;
    }
    
    const std::string& asString() const {
        if (type != STRING_TYPE) {
            throw std::runtime_error("Not a string");
        }
        return *data.stringVal;
    }
};

class JsonParser {
private:
    std::string input;
    size_t pos;
    
    void skipWhitespace() {
        while (pos < input.length() && std::isspace(input[pos])) {
            pos++;
        }
    }
    
    char peek() {
        skipWhitespace();
        if (pos >= input.length()) return '\0';
        return input[pos];
    }
    
    char consume() {
        skipWhitespace();
        if (pos >= input.length()) {
            throw std::runtime_error("Unexpected end of input");
        }
        return input[pos++];
    }
    
    std::string parseString() {
        if (consume() != '"') {
            throw std::runtime_error("Expected '\"'");
        }
        
        std::string result;
        while (pos < input.length() && input[pos] != '"') {
            result += input[pos++];
        }
        
        if (pos >= input.length()) {
            throw std::runtime_error("Unterminated string");
        }
        
        pos++;  // consume closing quote
        return result;
    }

public:
    explicit JsonParser(const std::string& json) : input(json), pos(0) {}
    
    JsonValue parse() {
        skipWhitespace();
        
        char c = peek();
        if (c == 'n') {
            // null
            pos += 4;
            return JsonValue();
        } else if (c == 't' || c == 'f') {
            // boolean
            if (c == 't') {
                pos += 4;
                return JsonValue(true);
            } else {
                pos += 5;
                return JsonValue(false);
            }
        } else if (c == '"') {
            // string
            return JsonValue(parseString());
        } else if (std::isdigit(c) || c == '-') {
            // number
            size_t end;
            double num = std::stod(input.substr(pos), &end);
            pos += end;
            return JsonValue(num);
        }
        
        throw std::runtime_error("Invalid JSON");
    }
};
