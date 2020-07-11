import contextlib
import shlex
import sys
import threading
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor

import click

SmallDCliRunnerContext = namedtuple("SmallDCliRunnerContext", ["runner", "message"])


def get_runner_context():
    return click.get_current_context().find_object(SmallDCliRunnerContext)


class SmallDCliRunner:
    def __init__(self, smalld, cli, prefix="", timeout=50, executor=None, **kwargs):
        self.smalld = smalld
        self.cli = cli
        self.prefix = prefix
        self.timeout = timeout
        self.conversations = {}
        self.executor = (
            executor if executor is not None else ThreadPoolExecutor(**kwargs)
        )

    def __enter__(self):
        self.smalld.on_message_create()(self.on_message)
        return self

    def __exit__(self, *args):
        self.executor.__exit__(*args)

    def on_message(self, msg):
        content = msg["content"]
        handle = self.conversations.pop((msg["author"]["id"], msg["channel_id"]), None)
        if handle is not None:
            handle.complete_with(content)
            return

        name, args = parse_command(self.prefix, content)
        if name != self.cli.name:
            return

        return self.executor.submit(self.handle_command, msg, args)

    def handle_command(self, msg, args):
        parent_ctx = click.Context(self.cli, obj=SmallDCliRunnerContext(self, msg))

        with parent_ctx, managed_click_execution() as manager:
            ctx = self.cli.make_context(self.cli.name, args, parent=parent_ctx)
            manager.enter_context(ctx)
            self.cli.invoke(ctx)

    def wait_for_message(self, msg):
        handle = Completable()
        author_id = msg["author"]["id"]
        channel_id = msg["channel_id"]
        self.conversations[(author_id, channel_id)] = handle

        if handle.wait(self.timeout):
            return handle.result
        else:
            self.conversations.pop((author_id, channel_id), None)
            raise TimeoutError("timed out while waiting for user response")


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
        except Exception as e:
            sys.excepthook(type(e), e, None)


class Completable:
    def __init__(self):
        self._condition = threading.Condition()
        self._result = None

    def wait(self, timeout=None):
        with self._condition:
            return self._condition.wait(timeout)

    def complete_with(self, result):
        with self._condition:
            self._result = result
            self._condition.notify()

    @property
    def result(self):
        with self._condition:
            return self._result


def echo(message="", *args, **kwargs):
    if not message:
        return

    runner, msg = get_runner_context()
    channel_id = msg["channel_id"]
    runner.smalld.post(f"/channels/{msg['channel_id']}/messages", {"content": message})


def prompt(message="", *args, **kwargs):
    runner, msg = get_runner_context()
    if message:
        echo(message, send=True)
    return runner.wait_for_message(msg)


click.echo = echo
click.core.echo = echo
click.utils.echo = echo
click.termui.echo = echo
click.decorators.echo = echo
click.exceptions.echo = echo

click.termui.visible_prompt_func = prompt
