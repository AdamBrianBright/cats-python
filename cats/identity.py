__all__ = [
    'Identity',
]


class Identity:
    @property
    def id(self) -> int:
        """
        Must return some sort of pointer that will help other code parts to address to this identity
        """
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        """
        Must return string describing the Identity type. Example: 'user'
        """
        raise NotImplementedError

    @property
    def sentry_scope(self) -> dict:
        """
        Must return dict of data that can be used by Sentry
        """
        raise NotImplementedError
