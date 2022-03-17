"""Utility module for asynchronous execution of system command."""
import asyncio
import atexit
import threading
import time
from typing import TYPE_CHECKING, Optional, Tuple

from pipeline.infrastructure import logging

if TYPE_CHECKING:
    from concurrent.futures import Future

LOG = logging.get_logger(__name__)


__all__ = [
    'close_event_loop',
    'schedule_task',
    'start_event_loop',
    'stop_event_loop',
]

# global variable to hold thread instance
ASYNC_THREAD = None
# ASYNC_OVERHEAD = 0
# ASYNC_EXEC = 0

# get event loop
def get_idling_loop():
    LOG.debug('Get event loop for pipeline execution.')
    default_loop = asyncio.get_event_loop()

    if default_loop.is_running():
        # create new idling loop
        LOG.debug('Default event loop is already running. Create another event loop for pipeline execution.')
        loop = asyncio.new_event_loop()
    else:
        loop = default_loop

    # workaround for a potential bug
    # no loop is attached to default child watcher
    # so explicitly attach the loop to default child watcher
    asyncio.events.get_child_watcher().attach_loop(loop)

    return loop


# pipeline specific event loop
ASYNC_LOOP = get_idling_loop()

# semaphore to limit number of concurrent process
ASYNC_SEMAPHORE = asyncio.Semaphore(20, loop=ASYNC_LOOP)


# running event loop on the thread
def loop_in_thread(loop: asyncio.AbstractEventLoop) -> None:
    """Run event loop.

    Args:
        loop: event loop instance
    """
    asyncio.set_event_loop(loop)
    loop.run_forever()


# create thread
def create_thread() -> threading.Thread:
    """Create thread.

    Returns:
        Thread instance
    """
    global ASYNC_LOOP
    return threading.Thread(target=loop_in_thread, args=(ASYNC_LOOP,))


# start event loop
def start_event_loop() -> None:
    """Start running event loop on the thread.

    If thread instance is not yet created, create it.
    """
    global ASYNC_THREAD

    if ASYNC_THREAD is None:
        ASYNC_THREAD = create_thread()

    if not ASYNC_THREAD.is_alive():
        LOG.debug('Starting event loop.')
        ASYNC_THREAD.start()


# stop event loop
def stop_event_loop() -> None:
    """Stop running event loop on the thread.

    Thread instance is destroyed.
    """
    global ASYNC_THREAD
    global ASYNC_LOOP

    if ASYNC_LOOP.is_closed():
        return

    if ASYNC_LOOP.is_running():
        # IMPORTANT: loop must be stopped via call_soon_threadsafe
        #
        # see StackOverflow article below
        # https://stackoverflow.com/questions/46093238/python-asyncio-event-loop-does-not-seem-to-stop-when-stop-method-is-called
        LOG.debug('Stopping event loop.')
        ASYNC_LOOP.call_soon_threadsafe(ASYNC_LOOP.stop)

    if ASYNC_THREAD is not None:
        ASYNC_THREAD.join()
        LOG.debug('thread alive ? %s', ASYNC_THREAD.is_alive())
    ASYNC_THREAD = None


# close event loop
def close_event_loop() -> None:
    """Close event loop.
    """
    global ASYNC_LOOP

    stop_event_loop()

    if not ASYNC_LOOP.is_closed():
        LOG.debug('Stopped event loop.')
        LOG.debug('Closing evnet loop...')
        ASYNC_LOOP.close()


# ensure to close thread for event loop
atexit.register(close_event_loop)


# run command in the event loop
async def run_command(cmd: Tuple[str], loop: asyncio.AbstractEventLoop) -> Optional[int]:
    """Run system command asynchronously.

    This is a coroutine to run system command asynchronously.

    Args:
        cmd: Command to run including arguments
        loop: Event loop

    Returns:
        Return code or None
    """
    global ASYNC_SEMAPHORE
    # global ASYNC_EXEC

    # LOG.debug('running command %s', cmd)
    # exec_start = time.time()

    # run system command asynchronously
    #
    # limit number of concurrent process using Semaphore
    # see https://stackoverflow.com/questions/52376095/blockingioerror-exception-ignored-should-i-be-concerned
    await ASYNC_SEMAPHORE.acquire()
    try:
        p = await asyncio.create_subprocess_exec(*cmd, loop=loop)
        result = await p.wait()
    finally:
        ASYNC_SEMAPHORE.release()
    # exec_end = time.time()
    # exec_duration = exec_end - exec_start
    # ASYNC_EXEC += exec_duration
    # LOG.info('execution took %s sec (%s sec in total)', exec_duration, ASYNC_EXEC)
    # LOG.debug('completed cmd result: %s', result)
    return result


def schedule_task(cmd: Tuple[str]) -> Optional['Future']:
    """Schedule execution of the command.

    Args:
        cmd: Command to run

    Returns:
        Future instance that encapsulates async execution of the command
        if event loop is running. Otherwise, return None.
    """
    global ASYNC_LOOP
    # global ASYNC_OVERHEAD
    if ASYNC_LOOP.is_running():
        # schedule_start = time.time()
        task = asyncio.run_coroutine_threadsafe(run_command(cmd, ASYNC_LOOP), ASYNC_LOOP)
        # schedule_end = time.time()
        # schedule_duration = schedule_end - schedule_start
        # ASYNC_OVERHEAD += schedule_duration
        # LOG.info('scheduling took %s sec (%s sec in total)', schedule_duration, ASYNC_OVERHEAD)
        return task
    else:
        return None


def wait_task(task: 'Future', timeout: Optional[float] = None) -> int:
    """Wait completion of the command encapsulated by Future.

    Args:
        task: Future instance that encapsulates async execution of the command
        timeout: Timeout value in sec. Defaults to no limit.

    Returns:
        Return code of the command
    """
    return task.result(timeout=timeout)


def cancel_task(task: 'Future', timeout: float = 1) -> bool:
    """Cancel execution of the command encapsulated by Future.

    Args:
        task: System command encapsulated by Future
        timeout: Timeout value in sec

    Returns:
        Whether or not cancel operation is successful
    """
    waiting = 0
    time_delta = 0.1

    while (not task.cancelled()) and waiting < timeout:
        if task.cancel():
            return True
        time.sleep(time_delta)
        waiting += time_delta

    # TODO: proper error handling is required
    # raise asyncio.TimeoutError

    return False
