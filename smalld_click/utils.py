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


click_prompt = click.prompt
click_echo = click.echo
click_visible_prompt_func = click.termui.visible_prompt_func
click_hidden_prompt_func = click.termui.hidden_prompt_func


echo_objects = (
    click,
    click.core,
    click.utils,
    click.termui,
    click.decorators,
    click.exceptions,
)
prompt_objects = (click, click.core, click.termui)


def set_click_functions(echo, prompt, visible_prompt, hidden_prompt):
    for obj in echo_objects:
        obj.echo = echo

    for obj in prompt_objects:
        obj.prompt = prompt

    click.termui.visible_prompt_func = visible_prompt
    click.termui.hidden_prompt_func = hidden_prompt


def patch_click_functions():
    set_click_functions(echo, prompt, prompt_func, prompt_func)


def restore_click_functions():
    set_click_functions(
        click_echo, click_prompt, click_visible_prompt_func, click_hidden_prompt_func
    )
