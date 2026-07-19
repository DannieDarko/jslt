from abc import ABC, abstractmethod

class JSON(ABC):
    @abstractmethod
    def __iter__(self):
        pass

    @abstractmethod
    def copy(self):
        pass

    @abstractmethod
    def to_json(self):
        pass

    @abstractmethod
    def current(self):
        pass
