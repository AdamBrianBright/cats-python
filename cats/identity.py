__all__ = [
    'Identity',
]


class IdentityMeta(type):
    __identity_registry__ = []

    def __new__(mcs, name, bases, attrs):
        cls = super().__new__(mcs, name, bases, attrs)
        IdentityMeta.__identity_registry__.append(cls)
        return cls

    @property
    def identity_list(cls):
        return IdentityMeta.__identity_registry__[:]


class Identity(metaclass=IdentityMeta):
    id: int
    model_name: str

    @property
    def sentry_scope(self) -> dict:
        """
        Must return dict of data that can be used by Sentry
        """
        raise NotImplementedError
