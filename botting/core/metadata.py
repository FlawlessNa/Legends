import multiprocessing.managers


class MetadataNamespace:
    """
    Namespaced view over a flat metadata DictProxy for shared state
    (non-proxy dicts). Automatically manages ignored_keys registration
    so the proxy monitor doesn't misinterpret shared state entries as
    pending proxy requests.
    """

    def __init__(
        self, metadata: multiprocessing.managers.DictProxy, prefix: str
    ) -> None:
        self._meta = metadata
        self._prefix = prefix

    def _key(self, name: str) -> str:
        return f"{self._prefix}/{name}"

    def get_shared_dict(self, name: str) -> dict:
        """
        Get or create a shared dict in metadata, auto-registered in ignored_keys.
        :param name: Name of the shared dict within this namespace.
        :return: The dict (a copy — must call set_shared_dict to persist changes).
        """
        key = self._key(name)
        if key not in self._meta:
            self._meta[key] = {}
            self._meta["ignored_keys"] = self._meta["ignored_keys"] | {key}
        return self._meta[key]

    def set_shared_dict(self, name: str, value: dict) -> None:
        """
        Persist an updated shared dict back to metadata.
        Required because DictProxy doesn't detect in-place mutations.
        :param name: Name of the shared dict within this namespace.
        :param value: The updated dict.
        """
        self._meta[self._key(name)] = value
