import time
from concurrent import futures
from unittest.mock import Mock, call

import click

import pytest
from smalld_click.smalld_click import SmallDCliRunner, get_runner_context

AUTHOR_ID = "author_id"
CHANNEL_ID = "channel_id"
DM_CHANNEL_ID = "dm_channel_id"
POST_MESSAGE_ROUTE = f"/channels/{CHANNEL_ID}/messages"
GET_DM_CHANNEL_ROUTE = "/users/@me/channels"
POST_DM_MESSAGE_ROUTE = f"/channels/{DM_CHANNEL_ID}/messages"
POST_OPEN_DM_ROUTE = "/users/@me/channels"


def make_message(content, author_id=AUTHOR_ID, channel_id=CHANNEL_ID):
    return {"content": content, "channel_id": channel_id, "author": {"id": author_id}}


def assert_completes(future, timeout=0.5):
    done, _ = futures.wait([future], timeout)
    if future not in done:
        raise AssertionError("timed out waiting for future to complete")


@pytest.fixture
def smalld():
    mock = Mock()

    def post_side_effect(route, data=None):
        if route == "/users/@me/channels":
            return {"id": DM_CHANNEL_ID}

    mock.post.side_effect = post_side_effect
    return mock


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
    f = subject.on_message(make_message("command"))

    assert_completes(f)
    smalld.post.assert_called_once_with(POST_MESSAGE_ROUTE, {"content": "echo\n"})


def test_buffers_calls_to_echo(subject, smalld):
    @click.command()
    def command():
        click.echo("echo 1")
        click.echo("echo 2")

    subject.cli = command
    f = subject.on_message(make_message("command"))

    assert_completes(f)
    smalld.post.assert_called_once_with(
        POST_MESSAGE_ROUTE, {"content": "echo 1\necho 2\n"}
    )


def test_should_not_send_empty_messages(subject, smalld):
    @click.command()
    def command():
        click.echo("  \n\n\n  ")

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
    f = subject.on_message(make_message("command"))
    subject.on_message(make_message("result"))

    assert_completes(f)
    smalld.post.assert_called_once_with(POST_MESSAGE_ROUTE, {"content": "prompt: "})


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

    f = subject.on_message(make_message("command"))
    time.sleep(0.2)
    subject.on_message(make_message("result"))
    time.sleep(0.2)
    subject.on_message(make_message("result"))

    assert_completes(f)
    smalld.post.assert_has_calls(
        [
            call(POST_MESSAGE_ROUTE, {"content": "echo 1\nprompt 1: "}),
            call(POST_MESSAGE_ROUTE, {"content": "prompt 2: "}),
            call(POST_MESSAGE_ROUTE, {"content": "echo 2\n"}),
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


def test_prompts_in_DM_for_hidden_prompts(subject, smalld):
    @click.command()
    def command():
        click.prompt("prompt", hide_input=True)

    subject.cli = command

    subject.on_message(make_message("command"))
    time.sleep(0.2)

    assert smalld.post.called_with(POST_DM_MESSAGE_ROUTE, {"content": "prompt: "})


def test_only_responds_to_hidden_prompts_answers_in_DM(subject, smalld):
    result = None

    @click.command()
    def command():
        nonlocal result
        result = click.prompt("prompt", hide_input=True)

    subject.cli = command

    f = subject.on_message(make_message("command"))
    time.sleep(0.2)
    subject.on_message(make_message("visible result"))
    subject.on_message(make_message("hidden result", channel_id=DM_CHANNEL_ID))

    assert_completes(f)
    assert result == "hidden result"


def test_continues_conversation_in_DM_after_hidden_prompt(subject, smalld):
    @click.command()
    def command():
        click.echo("echo 1")
        click.prompt("prompt", hide_input=True)
        click.echo("echo 2")

    subject.cli = command

    f = subject.on_message(make_message("command"))
    time.sleep(0.2)
    subject.on_message(make_message("result", channel_id=DM_CHANNEL_ID))

    assert_completes(f)
    assert smalld.post.call_count == 3
    smalld.post.assert_has_calls(
        [
            call(POST_OPEN_DM_ROUTE, {"recipient_id": AUTHOR_ID}),
            call(POST_DM_MESSAGE_ROUTE, {"content": "echo 1\nprompt: "}),
            call(POST_DM_MESSAGE_ROUTE, {"content": "echo 2\n"}),
        ]
    )
