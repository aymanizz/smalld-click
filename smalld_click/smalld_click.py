import contextlib
import logging
import shlex
import threading
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import click
from pkg_resources import get_distribution

__version__ = get_distribution("smalld-click").version


logger = logging.getLogger("smalld_click")


class SmallDCliRunnerContext:
    def __init__(self, runner, message):
        self.runner = runner
        self.message = message
        self.channel_id = message["channel_id"]
        self.echo_buffer = StringIO()
        self.buffered = True


def get_runner_context():
    return click.get_current_context().find_object(SmallDCliRunnerContext)


class SmallDCliRunner:
    def __init__(self, smalld, cli, prefix="", timeout=60, executor=None):
        self.smalld = smalld
        self.cli = cli
        self.prefix = prefix
        self.timeout = timeout
        self.conversations = {}
        self.executor = executor if executor is not None else ThreadPoolExecutor()

    def __enter__(self):
        self.smalld.on_message_create()(self.on_message)
        return self

    def __exit__(self, *args):
        self.executor.__exit__(*args)

    def on_message(self, msg):
        content = msg["content"]
        handle = self.conversations.pop((msg["author"]["id"], msg["channel_id"]), None)
        if handle is not None:
            handle.complete_with(msg)
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
            echo(flush=True, nl=False)

    def wait_for_message(self, author_id, channel_id):
        handle = Completable()
        self.conversations[(author_id, channel_id)] = handle

        if handle.wait(self.timeout):
            get_runner_context().message = handle.result
            return handle.result["content"]
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
        except:
            logger.exception("exception in command handler")


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


def echo(message=None, nl=True, file=None, *args, flush=False, **kwargs):
    ctx = get_runner_context()

    click_echo(message, file=ctx.echo_buffer, nl=nl, *args, **kwargs)
    if ctx.buffered and not flush:
        return

    content = ctx.echo_buffer.getvalue()
    if not content.strip():
        return
    ctx.echo_buffer = StringIO()

    smalld, channel_id = ctx.runner.smalld, ctx.channel_id
    smalld.post(f"/channels/{channel_id}/messages", {"content": content})


def prompt(text, default=None, hide_input=False, *args, **kwargs):
    ctx = get_runner_context()

    if hide_input:
        author_id = ctx.message["author"]["id"]
        channel = ctx.runner.smalld.post(
            "/users/@me/channels", {"recipient_id": author_id}
        )
        ctx.channel_id = channel["id"]

    return click_prompt(text, default, hide_input, *args, **kwargs)


def prompt_func(prompt="", *args, **kwargs):
    echo(prompt, nl=False, flush=True)

    ctx = get_runner_context()
    author_id = ctx.message["author"]["id"]
    return ctx.runner.wait_for_message(author_id, ctx.channel_id)


click_echo = click.echo
click_prompt = click.prompt

click.echo = echo
click.core.echo = echo
click.utils.echo = echo
click.termui.echo = echo
click.decorators.echo = echo
click.exceptions.echo = echo

click.prompt = prompt
click.termui.prompt = prompt
click.core.prompt = prompt

click.termui.visible_prompt_func = prompt_func
click.termui.hidden_prompt_func = prompt_func
