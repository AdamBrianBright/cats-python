class Identity:
    __identity_registry__ = []

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
    def sign_in_auto(cls, *args, **kwargs): ...

    def __init_subclass__(cls, **kwargs): ...
