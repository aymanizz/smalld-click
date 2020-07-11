import contextlib
import shlex
import sys
from collections import namedtuple

import click

SmallDCliRunnerContext = namedtuple("SmallDCliRunnerContext", ["runner", "message"])


def get_runner_context():
    return click.get_current_context().find_object(SmallDCliRunnerContext)


class SmallDCliRunner:
    def __init__(self, smalld, cli, prefix="", timeout=50, executor=None, **kwargs):
        self.smalld = smalld
        self.cli = cli
        self.prefix = prefix

    def __enter__(self):
        self.smalld.on_message_create(self.on_message)
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

        return self.handle_command(msg, args)

    def handle_command(self, msg, args):
        parent_ctx = click.Context(self.cli, obj=SmallDCliRunnerContext(self, msg))

        with parent_ctx, managed_click_execution() as manager:
            ctx = self.cli.make_context(self.cli.name, args, parent=parent_ctx)
            manager.enter_context(ctx)
            self.cli.invoke(ctx)


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


def echo(message="", *args, **kwargs):
    if not message:
        return

    runner, msg = get_runner_context()
    channel_id = msg["channel_id"]
    runner.smalld.post(f"/channels/{msg['channel_id']}/messages", {"content": message})


click.echo = echo
click.core.echo = echo
click.utils.echo = echo
click.termui.echo = echo
click.decorators.echo = echo
click.exceptions.echo = echo
