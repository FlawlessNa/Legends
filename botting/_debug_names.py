"""
Debugger-friendly naming for threads and asyncio tasks.

VS Code's Call Stack panel only ever shows three levels: the debug session, the
thread, and the frames. The session label for a child process is hardcoded by
debugpy as "Subprocess <pid>", and asyncio tasks are not threads, so neither the
process name nor the task name can reach the panel on their own. Both hooks below
work around that by encoding the information into the *thread* name, which is the
one label debugpy does report.

Enabled through the BOTTING_DEBUG_NAMES environment variable:
    unset / "0" / "false"   -> disabled
    "threads"               -> process-name tagging only (negligible cost)
    "1" / "true" / "tasks"  -> tagging + task-name mirroring (per-callback cost)
"""

import asyncio
import multiprocessing
import os
import threading

_ENV_VAR = "BOTTING_DEBUG_NAMES"
_TAG_ONLY = ("threads",)
_FULL = ("1", "true", "yes", "tasks")

_installed = False


def install() -> None:
    """
    Installs the hooks selected by BOTTING_DEBUG_NAMES, if any.
    Must run before any thread or event loop is created, which is why this is
    called at botting package import time.
    :return:
    """
    global _installed
    if _installed:
        return

    setting = os.environ.get(_ENV_VAR, "").strip().lower()
    if setting not in _TAG_ONLY + _FULL:
        return

    _installed = True
    tag_threads_with_process_name()
    if setting in _FULL:
        mirror_task_names_onto_threads()


def tag_threads_with_process_name() -> None:
    """
    Prefixes every thread name with the name of the process that owns it, so the
    Call Stack can be read without cross-referencing PIDs.
    Patching Thread.__init__ (rather than just renaming the current thread) is what
    catches the pool threads asyncio.to_thread spawns, which are otherwise named
    asyncio_0, asyncio_1, ... in every process alike.
    :return:
    """
    process_name = multiprocessing.current_process().name
    current = threading.current_thread()
    current.name = f"{process_name}|{current.name}"

    original_init = threading.Thread.__init__

    def _init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        self.name = f"{process_name}|{self.name}"

    threading.Thread.__init__ = _init


def mirror_task_names_onto_threads() -> None:
    """
    Appends the name of the currently running asyncio Task to the name of the thread
    running the event loop, for as long as that task's step is executing. A breakpoint
    hit inside a task then shows up as e.g. "Engine(Farmacy)|MainThread[Bot(Farmacy)]".
    Handle._run stays pure Python even when the C accelerated Task is in use, and every
    task step is dispatched through it, which makes it the one reliable hook point.
    :return:
    """
    original_run = asyncio.events.Handle._run

    def _run(self):
        callback_owner = getattr(self._callback, "__self__", None)
        thread = threading.current_thread()
        base = getattr(thread, "_botting_base_name", thread.name)
        thread._botting_base_name = base
        if isinstance(callback_owner, asyncio.Task):
            thread.name = f"{base}[{callback_owner.get_name()}]"
        try:
            return original_run(self)
        finally:
            thread.name = base

    asyncio.events.Handle._run = _run
