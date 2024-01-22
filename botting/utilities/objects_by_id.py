import ctypes


def get_object_by_id(obj_id: int) -> object:
    """
    Retrieves an object based on its ID.
    """
    return ctypes.cast(obj_id, ctypes.py_object).value
