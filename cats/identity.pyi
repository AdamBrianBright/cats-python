from typing import List


class Identity:
    identity_list: List[Identity]

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
