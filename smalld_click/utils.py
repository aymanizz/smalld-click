import threading

import click

from .conversation import get_conversation


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
    return get_conversation().say(*args, **kwargs)


def prompt(*args, **kwargs):
    return get_conversation().ask(*args, **kwargs)


def prompt_func(prompt):
    return get_conversation().get_reply(prompt)


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
