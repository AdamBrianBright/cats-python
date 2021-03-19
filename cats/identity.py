from asyncio import CancelledError

__all__ = [
    'Identity',
]


class Identity:
    __identity_registry__ = []

    id: int
    model_name: str

    @property
    def sentry_scope(self) -> dict:
        """
        Must return dict of data that can be used by Sentry
        """
        raise NotImplementedError

    @classmethod
    def sign_in(cls, *args, **kwargs):
        """
        Must return instance of self class if arguments match properly
        Raise exception otherwise
        """
        raise NotImplementedError

    def sign_out(self):
        """
        You may implement this method so it will do something if identity.sign_out() triggered
        """
        pass

    @classmethod
    def sign_in_auto(cls, *args, **kwargs):
        for identity in cls.__identity_registry__:
            try:
                res = identity.sign_in(*args, **kwargs)
                if res is not None:
                    return res
            except (KeyboardInterrupt, CancelledError):
                raise
            except Exception:
                pass
        return None

    def __init_subclass__(cls, **kwargs):
        cls.__identity_registry__.append(cls)
