import inspect


def get_methods(cls):
    for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        yield name, method
