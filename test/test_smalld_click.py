from concurrent.futures import Executor
from unittest.mock import Mock, patch

import click
import pytest
from smalld_click.smalld_click import (
    Completable,
    SmallDCliRunner,
    get_runner_context,
)


class ImmediateExecutor(Executor):
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


def make_message(content, channel_id="channel_id", author_id="author_id"):
    return {"content": content, "channel_id": channel_id, "author": {"id": author_id}}


@pytest.fixture(autouse=True)
def completable():
    with patch("smalld_click.smalld_click.Completable") as completable:
        yield completable.return_value


@pytest.fixture
def smalld():
    return Mock()


@pytest.fixture
def subject(smalld):
    with SmallDCliRunner(
        smalld, None, timeout=2, executor=ImmediateExecutor()
    ) as subject:
        yield subject


def test_exposes_correct_context(subject):
    ctx = None

    @click.command()
    def command():
        nonlocal ctx
        ctx = get_runner_context()

    subject.cli = command
    data = make_message("command")
    f = subject.on_message(data)

    assert ctx is not None
    assert ctx.runner is subject
    assert ctx.message is data


def test_parses_command(subject):
    argument, option = None, None

    @click.command()
    @click.argument("arg")
    @click.option("--opt")
    def command(arg, opt):
        nonlocal argument, option
        argument, option = arg, opt

    subject.cli = command
    f = subject.on_message(make_message("command argument --opt=option"))

    assert argument == "argument"
    assert option == "option"


def test_handles_echo(subject, smalld):
    @click.command()
    def command():
        click.echo("echo")

    subject.cli = command
    data = make_message("command")
    subject.on_message(data)

    smalld.post.assert_called_once_with(
        f"/channels/{data['channel_id']}/messages", {"content": "echo"}
    )


def test_handles_prompt(subject, smalld, completable):
    def wait_side_effect(timeout):
        return True

    @click.command()
    def command():
        click.prompt("prompt")

    completable.wait.side_effect = wait_side_effect
    subject.cli = command
    data = make_message("command")
    subject.on_message(data)
    subject.on_message(make_message("result"))

    smalld.post.assert_called_once_with(
        f"/channels/{data['channel_id']}/messages", {"content": "prompt: "}
    )
    completable.complete_with.assert_called_once_with("result")


def test_drops_conversation_when_timed_out(subject, completable):
    def wait_side_effect(timeout):
        return False

    completable.wait.side_effect = wait_side_effect

    @click.command()
    def command():
        click.prompt("prompt")

    subject.cli = command
    subject.on_message(make_message("command"))

    assert not subject.conversations
