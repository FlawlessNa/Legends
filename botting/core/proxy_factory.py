import logging
import multiprocessing.managers

logger = logging.getLogger(__name__)


class ProxyFactory:
    """
    Structured proxy request API that wraps the existing tuple-based protocol.
    Provides namespaced key management and automatic ignored_keys registration
    for shared (class-scoped) proxies.
    """

    def __init__(self, metadata: multiprocessing.managers.DictProxy) -> None:
        self._meta = metadata

    def _request(
        self,
        key: str,
        primitive_type: str,
        shared: bool,
        *args,
        **kwargs,
    ):
        """
        Core proxy request protocol. Writes a tuple into metadata, notifies
        the main process monitor, and waits for the tuple to be replaced
        with the actual proxy object.
        :param key: Unique key in metadata.
        :param primitive_type: Manager method name (e.g. "Lock", "Condition").
        :param shared: If True, the proxy persists in metadata (auto-added to
        ignored_keys). If False, it is popped after creation.
        :return: The created proxy object.
        """
        logger.debug("Requesting %s for %s.", primitive_type, key)
        notifier = self._meta["proxy_request"]
        with notifier:
            if key in self._meta and not isinstance(self._meta[key], tuple):
                logger.debug("Returning existing %s for %s.", primitive_type, key)
                return self._meta[key]

            self._meta[key] = (primitive_type, args, kwargs)
            while isinstance(self._meta[key], tuple):
                notifier.notify_all()
                notifier.wait(timeout=1)

        logger.debug("Created %s for %s.", primitive_type, key)
        if shared:
            self._meta["ignored_keys"] = self._meta["ignored_keys"] | {key}
            return self._meta[key]
        return self._meta.pop(key)

    def instance(self, owner: str, primitive_type: str, *args, **kwargs):
        """
        Instance-scoped proxy. Popped from metadata after creation.
        Use for per-bot locks and conditions.
        :param owner: Identifier for the owning instance (e.g. repr(self)).
        :param primitive_type: Manager method name (e.g. "Lock", "Condition").
        :return: The created proxy object.
        """
        key = f"proxy/instance/{owner}/{primitive_type}"
        return self._request(key, primitive_type, False, *args, **kwargs)

    def shared(self, group: str, name: str, primitive_type: str, *args, **kwargs):
        """
        Class-scoped shared proxy. Persists in metadata and is auto-registered
        in ignored_keys. Use for cross-bot synchronization primitives.
        :param group: Group name, typically the DecisionMaker class name.
        :param name: Descriptive name for this proxy within the group.
        :param primitive_type: Manager method name (e.g. "Lock", "Event").
        :return: The created proxy object.
        """
        key = f"proxy/shared/{group}/{name}"
        return self._request(key, primitive_type, True, *args, **kwargs)
