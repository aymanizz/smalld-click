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
        self,
        smalld,
        cli,
        prefix="",
        name=None,
        timeout=60,
        create_message=None,
        executor=None,
    ):
        self.smalld = smalld
        self.cli = cli
        self.prefix = prefix
        self.name = name if name is not None else cli.name or ""
        self.timeout = timeout
        self.create_message = create_message if create_message else plain_message
        self.executor = executor if executor else ThreadPoolExecutor()
        self.pending = {}

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

        handle = self.pending.pop((user_id, channel_id), None)
        if handle is not None:
            handle.complete_with(msg)
            return

        if not content.startswith(self.prefix + self.name):
            return
        command = content[len(self.prefix) :].lstrip()

        return self.executor.submit(self.handle_command, msg, command)

    def handle_command(self, msg, command):
        with managed_click_execution() as manager:
            conversation = Conversation(self, msg)
            parent_ctx = click.Context(self.cli, obj=conversation)

            manager.enter_context(parent_ctx)
            manager.enter_context(conversation)

            args, error = parse_command(command)
            if args is None:
                return

            ctx = self.cli.make_context(
                self.prefix + self.name, args or [], parent=parent_ctx
            )
            manager.enter_context(ctx)

            if error:
                ctx.fail(error)

            self.cli.invoke(ctx)

    def wait_for_message(self, user_id, channel_id):
        handle = Completable()
        self.pending[(user_id, channel_id)] = handle
        if handle.wait(self.timeout):
            return handle.result
        else:
            self.pending.pop((user_id, channel_id), None)
            raise TimeoutError("timed out while waiting for user response")


def plain_message(msg):
    return {"content": msg}


def parse_command(name, command):
    if name:
        name, *rest = command.split(maxsplit=1)
        if name != name:
            return None, None
        command = "".join(rest)

    args = None
    error = None
    try:
        args = shlex.split(command)
    except ValueError as e:
        error = e.args[0]

    return args, error


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
