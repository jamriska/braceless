#include <iostream>

template <typename T>
class LinkedList {
    struct Node {
        T data;
        Node* next;
        
        Node(T value) : data(value), next(nullptr) {}
    };
    
    Node* head;
    int size;
    
public:
    LinkedList() : head(nullptr), size(0) {}
    
    ~LinkedList() {
        while (head) {
            Node* temp = head;
            head = head->next;
            delete temp;
        }
    }
    
    void push_front(T value) {
        Node* newNode = new Node(value);
        newNode->next = head;
        head = newNode;
        size++;
    }
    
    void push_back(T value) {
        if (!head) {
            push_front(value);
            return;
        }
        
        Node* current = head;
        while (current->next) {
            current = current->next;
        }
        
        current->next = new Node(value);
        size++;
    }
    
    bool remove(T value) {
        if (!head) return false;
        
        if (head->data == value) {
            Node* temp = head;
            head = head->next;
            delete temp;
            size--;
            return true;
        }
        
        Node* current = head;
        while (current->next) {
            if (current->next->data == value) {
                Node* temp = current->next;
                current->next = temp->next;
                delete temp;
                size--;
                return true;
            }
            current = current->next;
        }
        
        return false;
    }
    
    void print() {
        Node* current = head;
        std::cout << "[";
        while (current) {
            std::cout << current->data;
            if (current->next) {
                std::cout << " -> ";
            }
            current = current->next;
        }
        std::cout << "]" << std::endl;
    }
    
    int getSize() {
        return size;
    }
};
