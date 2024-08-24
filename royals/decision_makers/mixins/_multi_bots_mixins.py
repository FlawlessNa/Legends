import logging
import multiprocessing.managers
from botting import PARENT_LOG
from botting.core import DecisionMaker

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.INFO


class SharedProxyMixin:
    pass
    # @staticmethod
    # def request_proxy(
    #     metadata: multiprocessing.managers.DictProxy,
    #     requester: str,
    #     primitive_type: str,
    #     *args,
    #     **kwargs,
    # ):
    #     """
    #     Overrides the DecisionMaker.request_proxy method such that the requested object
    #     is created once in the manager process and then retained within the metadata
    #     for all identical requester to use.
    #     :param metadata: An EventProxy object that is set to notify the Manager of the
    #     request.
    #     :param requester: a string representing the requester.
    #     :param primitive_type: a string representing the primitive type.
    #     :return: a Proxy instance.
    #     """
    # TODO - Needs to work in a multiprocessing context.
    # Might just be easier to add param into DecisionMaker.request_proxy
    # that prevents from popping the metadata.

    # proxy = metadata.get(requester, None)
    # if proxy is not None and not isinstance(proxy, tuple):
    #     return proxy
    # return proxy if proxy is not None else DecisionMaker.request_proxy(
    #     metadata, requester, primitive_type, *args, **kwargs
    # )
