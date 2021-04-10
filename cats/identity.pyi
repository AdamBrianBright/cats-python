from typing import List, Type


class IdentityMeta(type):
    __identity_registry__: List[Type['Identity']] = []

    def __new__(mcs, name, bases, attrs): ...

    @property
    def identity_list(cls) -> List[Type['Identity']]: ...


class Identity(metaclass=IdentityMeta):
    @property
    def id(self) -> int:
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        raise NotImplementedError

    @property
    def sentry_scope(self) -> dict:
        """
        Must return dict of data that can be used by Sentry
        """
        raise NotImplementedError
