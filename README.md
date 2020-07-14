# SmallD-Click

[![PyPI version](https://badge.fury.io/py/smalld-click.svg)](https://badge.fury.io/py/smalld-click)
![Build](https://github.com/aymanizz/smalld-click/workflows/Build/badge.svg?branch=master)
[![Maintainability](https://api.codeclimate.com/v1/badges/e2fdfe214c0fa6feb9de/maintainability)](https://codeclimate.com/github/aymanizz/smalld-click/maintainability)
[![Test Coverage](https://api.codeclimate.com/v1/badges/e2fdfe214c0fa6feb9de/test_coverage)](https://codeclimate.com/github/aymanizz/smalld-click/test_coverage)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://conventionalcommits.org)
[![Discord](https://img.shields.io/discord/417389758470422538)](https://discord.gg/3aTVQtz)


SmallD-Click is an extension for [SmallD](https://github.com/princesslana/smalld.py) that enables the use of
[Click](https://click.palletsprojects.com/) CLI applications as discord bots.

## Installing

Install using pip:

```console
$ pip install smalld-click
```

## Example

```python
import click

from smalld import SmallD
from smalld_click import SmallDCliRunner


@click.command()
@click.option("--count", default=1, help="Number of greetings.")
@click.option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for x in range(count):
        click.echo("Hello %s!" % name)


smalld = SmallD()

with SmallDCliRunner(smalld, hello, prefix="++"):
    smalld.run()
```

For this CLI example, if a user sends the message "++hello --count=2", then the bot will ask the user -
by sending a message in the same channel - for their name, "Your name:".

If the user answers with "lymni", for example, the bot will send the message, "Hello lymni", twice.

Notice that the bot responds in a single message, instead of two, even though we call `click.echo` multiple times.
This is because calls to echo are buffered. However, calls to prompt will cause this buffer to be flushed and its
content is sent immediately.

![Example Run](https://raw.githubusercontent.com/aymanizz/smalld-click/master/examples/example_run.png)

There is also a timeout for how long the bot will wait for the user's message, if the timeout is exceeded the bot will
simply drop the execution of the command.

## Guide

```python
SmallDCliRunner(smalld, cli, prefix="", timeout=60, executor=None)
```

The `SmallDCliRunner` is the core class for running CLI applications.

- `smalld` the SmallD instance for your bot.
- `prefix` used to determine what messages to consider as invocations of the CLI application.
- `timeout` how long will the bot wait for the user to respond to a prompt in seconds.
- `executor` an instance of `concurrent.futures.Executor` used to execute commands. by default
    this is a `concurrent.futures.ThreadPoolExecutor`.

Instances of this class should be used as a context manager, to patch click functions and to properly close
the executor when the bot stops.

```python
Conversation(runner, message)
```

Represents the the state of the command invocation. Holds the runner instance, and the message payload.
Also manages the interactions between the user and the CLI application.

After each prompt, the message is updated to the latest message sent by the user.

```python
get_conversation()
```

Returns the current conversation. Must only be invoked inside of a command handler.

### Patched functionality

You can use `click.echo`, and `click.prompt` directly to send/wait for messages.

prompts that are hidden, using `hide_input=True`, are sent to the user DM, and cause the conversation to continue there.

Note that, echo and prompt will send a message in the same channel as the message that triggered the command invocation.

Calls to echo are buffered, the buffer is flushed either when there is a prompt or when the command finishes execution.
It's also possible to flush the buffer by passing `flush=True` to `click.echo` call.

## Acknowledgements

Original idea by [Princess Lana](https://github.com/ianagbip1oti).

## Contributing

* [Tox](https://tox.readthedocs.io/) is used for running tests.
  * Run `tox -e` to run tests with your installed python version
  * Run `tox -e fmt` to format the code
* [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) is used for commit messages and pull requests

### Developing

Tox is used to setup and manage virtual environments when working on SmallD-Click

To run tests:
```console
$ tox
```

To run the examples greet bot:
```console
$ tox -e run -- examples/greet.py
```
