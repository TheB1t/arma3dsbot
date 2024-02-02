import json

class Cache:
    def __init__(self, filename="cache.json"):
        self._data      = {}
        self._filename  = filename
    
    def load(self):
        try:
            with open(self._filename, 'r') as file:
                self._data = json.load(file)
                
            return True
        except FileNotFoundError:
            return False

    def save(self):
        with open(self._filename, 'w') as file:
            json.dump(self._data, file, indent=4)
        
    def __getattr__(self, key):
        if key in self._data:
            return self._data[key]
        elif hasattr(super(), key):
            return getattr(super(), key)
        else:
            raise AttributeError(f"'Cache' object has no attribute '{key}'")

    def __setattr__(self, key, value):
        if key.startswith('_'):
            super().__setattr__(key, value)
        else:
            self._data[key] = value
            self.save()

    def __hasattr__(self, key):
        return key in self._data or hasattr(super(), key)

    def __contains__(self, key):
        return key in self._data
