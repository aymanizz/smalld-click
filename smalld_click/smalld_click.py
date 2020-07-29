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

        args = parse_command(self.prefix, self.name, content)
        if args is None:
            return

        return self.executor.submit(self.handle_command, msg, args)

    def handle_command(self, msg, args):
        info_name = self.prefix + self.name
        with managed_click_execution() as manager:
            conversation = Conversation(self, msg)
            parent_ctx = click.Context(self.cli, info_name=info_name, obj=conversation)

            manager.enter_context(parent_ctx)
            manager.enter_context(conversation)

            args_list = split_args(args)
            ctx = self.cli.make_context("", args_list, parent=parent_ctx)
            manager.enter_context(ctx)

            self.cli.invoke(ctx)

    def wait_for_message(self, user_id, channel_id):
        handle = Completable()
        self.pending[(user_id, channel_id)] = handle
        if handle.wait(self.timeout):
            return handle.result
        self.pending.pop((user_id, channel_id), None)
        raise TimeoutError("timed out while waiting for user response")


def plain_message(msg):
    return {"content": msg}


def parse_command(prefix, name, message):
    if not message.startswith(prefix):
        return
    cmd = message[len(prefix) :].lstrip()
    if not name:
        return cmd
    cmd_name, *rest = cmd.split(maxsplit=1)
    if cmd_name != name:
        return
    return "".join(rest)


def split_args(command):
    try:
        return shlex.split(command)
    except ValueError as e:
        click.get_current_context().fail(e.args[0])


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
