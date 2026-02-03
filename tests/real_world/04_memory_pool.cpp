#include <cstddef>
#include <cstdlib>
#include <stdexcept>

template <typename T, size_t BlockSize = 4096>
class MemoryPool {
private:
    union Slot {
        T element;
        Slot* next;
    };
    
    struct Block {
        Block* next;
        Slot slots[BlockSize];
    };
    
    Slot* freeSlots;
    Block* blocks;
    size_t allocatedCount;
    size_t totalCapacity;
    
    void allocateBlock() {
        Block* newBlock = static_cast<Block*>(std::malloc(sizeof(Block)));
        if (!newBlock) {
            throw std::bad_alloc();
        }
        
        newBlock->next = blocks;
        blocks = newBlock;
        
        // Link all slots in the new block to free list
        for (size_t i = 0; i < BlockSize - 1; i++) {
            newBlock->slots[i].next = &newBlock->slots[i + 1];
        }
        
        newBlock->slots[BlockSize - 1].next = freeSlots;
        freeSlots = &newBlock->slots[0];
        totalCapacity += BlockSize;
    }

public:
    MemoryPool() : freeSlots(nullptr), blocks(nullptr), 
                   allocatedCount(0), totalCapacity(0) {
        allocateBlock();
    }
    
    ~MemoryPool() {
        Block* current = blocks;
        while (current) {
            Block* next = current->next;
            std::free(current);
            current = next;
        }
    }
    
    template <typename... Args>
    T* construct(Args&&... args) {
        if (!freeSlots) {
            allocateBlock();
        }
        
        Slot* slot = freeSlots;
        freeSlots = slot->next;
        allocatedCount++;
        
        // Construct object in-place
        return new (&slot->element) T(std::forward<Args>(args)...);
    }
    
    void destroy(T* ptr) {
        if (!ptr) return;
        
        // Call destructor
        ptr->~T();
        
        // Return slot to free list
        Slot* slot = reinterpret_cast<Slot*>(ptr);
        slot->next = freeSlots;
        freeSlots = slot;
        allocatedCount--;
    }
    
    size_t getAllocatedCount() const { return allocatedCount; }
    size_t getTotalCapacity() const { return totalCapacity; }
    size_t getAvailableCount() const { return totalCapacity - allocatedCount; }
    
    float getFragmentation() const {
        if (totalCapacity == 0) return 0.0f;
        return 1.0f - static_cast<float>(allocatedCount) / totalCapacity;
    }
};

// Example usage with a custom class
class GameObject {
private:
    int id;
    float x, y, z;
    bool active;
    
public:
    GameObject(int id, float x, float y, float z) 
        : id(id), x(x), y(y), z(z), active(true) {}
    
    void update(float deltaTime) {
        if (active) {
            x += deltaTime;
            y += deltaTime * 0.5f;
        }
    }
    
    bool isActive() const { return active; }
    void setActive(bool state) { active = state; }
    int getId() const { return id; }
};
