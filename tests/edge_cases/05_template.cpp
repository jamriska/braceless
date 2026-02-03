template <typename T>
class Container {
    T data;
    
    void set(T value) {
        data = value;
    }
    
    T get() {
        return data;
    }
};
