from concurrent import futures
from unittest.mock import Mock, call

import click
import time

import pytest
from smalld_click.smalld_click import SmallDCliRunner, get_runner_context


def make_message(content, channel_id="channel_id", author_id="author_id"):
    return {"content": content, "channel_id": channel_id, "author": {"id": author_id}}


def assert_completes(future, timeout=0.2):
    done, _ = futures.wait([future], timeout)
    if future not in done:
        raise AssertionError("timed out waiting for future to complete")


@pytest.fixture
def smalld():
    return Mock()


@pytest.fixture
def subject(smalld):
    with SmallDCliRunner(smalld, None, timeout=1) as subject:
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

    assert_completes(f)
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

    assert_completes(f)
    assert argument == "argument"
    assert option == "option"


def test_handles_echo(subject, smalld):
    @click.command()
    def command():
        click.echo("echo")

    subject.cli = command
    data = make_message("command")
    f = subject.on_message(data)

    assert_completes(f)
    smalld.post.assert_called_once_with(
        f"/channels/{data['channel_id']}/messages", {"content": "echo\n"}
    )


def test_buffers_calls_to_echo(subject, smalld):
    @click.command()
    def command():
        click.echo("echo 1")
        click.echo("echo 2")

    subject.cli = command
    data = make_message("command")
    f = subject.on_message(data)

    assert_completes(f)
    smalld.post.assert_called_once_with(
        f"/channels/{data['channel_id']}/messages", {"content": "echo 1\necho 2\n"}
    )


def test_should_not_send_empty_messages(subject, smalld):
    @click.command()
    def command():
        click.echo("")

    subject.cli = command
    f = subject.on_message(make_message("command"))

    assert_completes(f)
    assert smalld.post.call_count == 0


def test_handles_prompt(subject, smalld):
    result = None

    @click.command()
    def command():
        nonlocal result
        result = click.prompt("prompt")

    subject.cli = command
    data = make_message("command")
    f = subject.on_message(data)
    subject.on_message(make_message("result"))

    assert_completes(f)
    smalld.post.assert_called_once_with(
        f"/channels/{data['channel_id']}/messages", {"content": "prompt: "}
    )


def test_sends_prompts_without_buffering(subject, smalld):
    result1, result2 = None, None

    @click.command()
    def command():
        nonlocal result1, result2
        click.echo("echo 1")
        result1 = click.prompt("prompt 1")
        result2 = click.prompt("prompt 2")
        click.echo("echo 2")

    subject.cli = command
    data = make_message("command")
    route = f"/channels/{data['channel_id']}/messages"

    f = subject.on_message(data)
    time.sleep(0.2)
    subject.on_message(make_message("result"))
    time.sleep(0.2)
    subject.on_message(make_message("result"))

    assert_completes(f)
    smalld.post.assert_has_calls(
        [
            call(route, {"content": "echo 1\nprompt 1: "}),
            call(route, {"content": "prompt 2: "}),
            call(route, {"content": "echo 2\n"}),
        ]
    )
    assert result1 == result2 == "result"


def test_drops_conversation_when_timed_out(subject):
    @click.command()
    def command():
        click.prompt("prompt")

    subject.cli = command
    subject.timeout = 0.2

    f = subject.on_message(make_message("command"))

    assert_completes(f)
    assert not subject.conversations
