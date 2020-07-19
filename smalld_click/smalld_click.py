import contextlib
import logging
import shlex
from concurrent.futures import ThreadPoolExecutor

import click
from pkg_resources import get_distribution

from .conversation import Conversation
from .utils import Completable, patch_click_functions, restore_click_functions

__version__ = get_distribution("smalld-click").version


logger = logging.getLogger("smalld_click")


class SmallDCliRunner:
    def __init__(
        self, smalld, cli, prefix="", timeout=60, create_message=None, executor=None,
    ):
        self.smalld = smalld
        self.cli = cli
        self.prefix = prefix
        self.timeout = timeout
        self.create_message = create_message if create_message else plain_message
        self.executor = executor if executor else ThreadPoolExecutor()
        self.listeners = {}

    def __enter__(self):
        patch_click_functions()
        self.smalld.on_message_create()(self.on_message)
        return self

    def __exit__(self, *args):
        restore_click_functions()
        self.executor.__exit__(*args)

    def on_message(self, msg):
        content = msg["content"]
        user_id = msg["author"]["id"]
        channel_id = msg["channel_id"]

        handle = self.remove_listener(user_id, channel_id)
        if handle is not None:
            handle.complete_with(msg)
            return

        name, args = parse_command(self.prefix, content)
        if name != self.cli.name:
            return

        return self.executor.submit(self.handle_command, msg, args)

    def handle_command(self, msg, args):
        with managed_click_execution() as manager:
            conversation = Conversation(self, msg)
            parent_ctx = click.Context(self.cli, obj=conversation)

            manager.enter_context(parent_ctx)
            manager.enter_context(conversation)

            ctx = self.cli.make_context(self.cli.name, args, parent=parent_ctx)
            manager.enter_context(ctx)

            self.cli.invoke(ctx)

    def add_listener(self, user_id, channel_id):
        handle = Completable()
        self.listeners[(user_id, channel_id)] = handle
        return handle

    def remove_listener(self, user_id, channel_id):
        return self.listeners.pop((user_id, channel_id), None)


def plain_message(msg):
    return {"content": msg}


def parse_command(prefix, command):
    cmd = command.strip()[len(prefix) :].lstrip()
    if not command.startswith(prefix) or not cmd:
        return None, []

    args = shlex.split(cmd)
    return args[0], args[1:]


@contextlib.contextmanager
def managed_click_execution():
    with contextlib.ExitStack() as es:
        try:
            yield es
        except click.exceptions.ClickException as e:
            e.show()
        except (click.exceptions.Exit, click.exceptions.Abort) as e:
            pass
        except TimeoutError:
            pass
        except:
            logger.exception("exception in command handler")
