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
    def __init__(self, runner, message, timeout):
        self.runner = runner
        self.smalld = runner.smalld
        self.message = message
        self.timeout = timeout
        self.channel_id = message["channel_id"]
        self.user_id = message["author"]["id"]
        self.echo_buffer = StringIO()
        self.is_safe = False

    def ensure_safe(self):
        if self.is_safe:
            return

        channel = self.runner.smalld.post(
            "/users/@me/channels", {"recipient_id": self.user_id}
        )
        self.channel_id = channel["id"]
        self.is_safe = True

    def say(self, message=None, nl=True, file=None, *args, flush=False, **kwargs):
        click_echo(message, file=self.echo_buffer, nl=nl, *args, **kwargs)
        if flush:
            self.flush()

    def ask(self, text, default=None, hide_input=False, *args, **kwargs):
        if hide_input:
            self.ensure_safe()
        return click_prompt(text, default, hide_input, *args, **kwargs)

    def get_reply(self, prompt):
        self.say(prompt, nl=False, flush=True)
        return self.wait_for_message()

    def flush(self):
        content = self.echo_buffer.getvalue()
        self.echo_buffer = StringIO()
        if not content.strip():
            return

        smalld, channel_id = self.runner.smalld, self.channel_id
        smalld.post(f"/channels/{channel_id}/messages", {"content": content})

    def wait_for_message(self):
        handle = self.runner.add_pending(self.user_id, self.channel_id)
        if handle.wait(self.timeout):
            self.message = handle.result
            return handle.result["content"]
        else:
            self.runner.remove_pending(self.user_id, self.channel_id)
            raise TimeoutError("timed out while waiting for user response")

    def close(self):
        self.__exit__(None, None, None)
        get_current_context().abort()

    def __enter__(self):
        return self
    
    def __exit__(self, type, value, traceback):
        self.flush()


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
        user_id = msg["author"]["id"]
        channel_id = msg["channel_id"]

        handle = self.remove_pending(user_id, channel_id)
        if handle is not None:
            handle.complete_with(msg)
            return

        name, args = parse_command(self.prefix, content)
        if name != self.cli.name:
            return

        return self.executor.submit(self.handle_command, msg, args)

    def handle_command(self, msg, args):
        parent_ctx = click.Context(self.cli, obj=SmallDCliRunnerContext(self, msg, self.timeout))

        with parent_ctx, managed_click_execution() as manager:
            ctx = self.cli.make_context(self.cli.name, args, parent=parent_ctx)
            manager.enter_context(ctx)
            self.cli.invoke(ctx)
            echo(flush=True, nl=False)

    def add_pending(self, user_id, channel_id):
        handle = Completable()
        self.conversations[(user_id, channel_id)] = handle
        return handle

    def remove_pending(self, user_id, channel_id):
        return self.conversations.pop((user_id, channel_id), None)


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


def echo(*args, **kwargs):
    return get_runner_context().say(*args, **kwargs)


def prompt(*args, **kwargs):
    return get_runner_context().ask(*args, **kwargs)


def prompt_func(prompt):
    return get_runner_context().get_reply(prompt)

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
