from botting.models_abstractions import BaseMob


class MapleMob:
    """
    Factory that creates BaseMob subclasses by name.
    The name is the mob's in-game display name as a string (e.g. "PackPinky").
    Detection attributes (_filter, _preprocess_img, etc.) default to None and
    are expected to be provided by a trained ML model at runtime.
    """
    _created_classes: dict[str, type] = {}

    def __new__(cls, mob_name: str) -> BaseMob:
        return cls.create(mob_name)

    @classmethod
    def create(cls, mob_name: str) -> BaseMob:
        if mob_name not in cls._created_classes:
            mob_class = type(
                mob_name,
                (BaseMob,),
                {'_filter': None, '_preprocess_img': None},
            )
            cls._created_classes[mob_name] = mob_class
        return cls._created_classes[mob_name]()
