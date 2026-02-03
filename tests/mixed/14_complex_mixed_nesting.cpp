class DataProcessor {
    std::vector<int> data;
    
    void process() {
        for (int i = 0; i < data.size(); i++) {
            if (data[i] > 0) {
                try {
                    validate(data[i]);
                } catch (std::exception& e) {
                    log_error(e.what());
                    continue;
                }
            } else {
                skip();
            }
        }
    }
};
