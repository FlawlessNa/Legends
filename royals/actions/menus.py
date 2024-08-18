import multiprocessing.synchronize

from botting import controller
from royals.model.interface import Minimap


def toggle_menu(
    handle: int,
    ign: str,
    config_name: str,
):
    pass


def toggle_minimap(
    handle: int,
    ign: str,
):
    return toggle_menu(handle, ign, 'Minimap Toggle')


def ensure_minimap_displayed(
    handle: int,
    ign: str,
    minimap: Minimap,
    lock: multiprocessing.synchronize.Lock,
    **kwargs
):
    import time
    print('Ensuring minimap from process', multiprocessing.current_process().name)
    time.sleep(10)
    breakpoint()
    # while not minimap.is_displayed(handle, **kwargs):
    #     toggle_minimap(handle, ign)