import time
from concurrent import futures
from functools import partial
from unittest.mock import Mock, call

import click

import pytest
from smalld_click import SmallDCliRunner, get_conversation

AUTHOR_ID = "author_id"
CHANNEL_ID = "channel_id"
DM_CHANNEL_ID = "dm_channel_id"
POST_MESSAGE_ROUTE = f"/channels/{CHANNEL_ID}/messages"
GET_DM_CHANNEL_ROUTE = "/users/@me/channels"
POST_DM_MESSAGE_ROUTE = f"/channels/{DM_CHANNEL_ID}/messages"
POST_OPEN_DM_ROUTE = "/users/@me/channels"


def make_message(content, author_id=AUTHOR_ID, channel_id=CHANNEL_ID):
    return {"content": content, "channel_id": channel_id, "author": {"id": author_id}}


def assert_completes(future_or_futures, timeout=0.5):
    futures_list = (
        future_or_futures
        if hasattr(future_or_futures, "__iter__")
        else [future_or_futures]
    )
    done, _ = futures.wait(futures_list, timeout)
    if any(future not in done for future in futures_list):
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
def make_subject(request, smalld):
    def factory(*args, **kwargs):
        kwargs.setdefault("timeout", 1)
        subject = SmallDCliRunner(smalld, *args, **kwargs).__enter__()
        request.addfinalizer(partial(subject.__exit__, None, None, None))
        return subject

    return factory


def test_raises_error_for_empty_prefix_and_name(make_subject):
    @click.command()
    def command():
        pass

    with pytest.raises(ValueError) as exc_info:
        make_subject(command, prefix="", name="")


def test_exposes_correct_context(make_subject):
    conversation = None

    @click.command()
    def command():
        nonlocal conversation
        conversation = get_conversation()

    subject = make_subject(command)
    data = make_message("command")
    f = subject.on_message(data)

    assert_completes(f)
    assert conversation is not None
    assert conversation.runner is subject
    assert conversation.message is data


def test_parses_command(make_subject):
    argument, option = None, None

    @click.command()
    @click.argument("arg")
    @click.option("--opt")
    def command(arg, opt):
        nonlocal argument, option
        argument, option = arg, opt

    subject = make_subject(command)
    f = subject.on_message(make_message("command argument --opt=option"))

    assert_completes(f)
    assert argument == "argument"
    assert option == "option"


def test_parses_multicommands(make_subject):
    slots = [False, False]

    @click.group()
    def cli():
        pass

    def create_command(slot):
        @cli.command(name=f"cmd{slot}")
        @click.option("--opt", is_flag=True)
        def cmd(opt):
            nonlocal slots
            if opt:
                slots[slot] = True

    create_command(0)
    create_command(1)

    cli_collection = click.CommandCollection(sources=[cli])
    subject = make_subject(cli_collection, prefix="$")

    f1 = subject.on_message(make_message("$cmd0 --opt"))
    f2 = subject.on_message(make_message("$cmd1 --opt"))
    assert_completes([f1, f2])
    assert all(slots)


@pytest.mark.parametrize(
    "prefix, name, message, expected",
    [
        ("++", "", "", False),
        ("++", "", "++", True),
        ("++", "", "++arg", True),
        ("++", "", "++  arg", True),
        ("++", "", "++--opt arg", True),
        ("", "invoke", "", False),
        ("", "invoke", "invoke", True),
        ("", "invoke", "invoke arg", True),
        ("", "invoke", "invokearg", False),
        ("", "invoke", "invoke --opt", True),
        ("", "invoke", "invoke--opt arg", False),
        ("++", "invoke", "", False),
        ("++", "invoke", "++", False),
        ("++", "invoke", "++invoke", True),
        ("++", "invoke", "++  invoke", True),
        ("++", "invoke", "++invoke arg", True),
        ("++", "invoke", None, False),
    ],
)
def test_parses_name_and_prefix_correctly(
    make_subject, prefix, name, message, expected
):
    called = False

    @click.command()
    @click.argument("arg", required=False)
    @click.option("--opt", is_flag=True)
    def cli(arg, opt):
        nonlocal called
        called = True

    subject = make_subject(cli, prefix=prefix, name=name)
    f = subject.on_message(make_message(message))

    assert_completes(f) if expected else time.sleep(0.2)
    assert called is expected


def test_handles_echo(make_subject, smalld):
    @click.command()
    def command():
        click.echo("echo")

    subject = make_subject(command)
    f = subject.on_message(make_message("command"))

    assert_completes(f)
    smalld.post.assert_called_once_with(POST_MESSAGE_ROUTE, {"content": "echo\n"})


def test_buffers_calls_to_echo(make_subject, smalld):
    @click.command()
    def command():
        click.echo("echo 1")
        click.echo("echo 2")

    subject = make_subject(command)
    f = subject.on_message(make_message("command"))

    assert_completes(f)
    smalld.post.assert_called_once_with(
        POST_MESSAGE_ROUTE, {"content": "echo 1\necho 2\n"}
    )


def test_should_not_send_empty_messages(make_subject, smalld):
    @click.command()
    def command():
        click.echo("  \n\n\n  ")

    subject = make_subject(command)
    f = subject.on_message(make_message("command"))

    assert_completes(f)
    assert smalld.post.call_count == 0


def test_handles_prompt(make_subject, smalld):
    result = None

    @click.command()
    def command():
        nonlocal result
        result = click.prompt("prompt")

    subject = make_subject(command)
    f = subject.on_message(make_message("command"))
    time.sleep(0.2)
    subject.on_message(make_message("result"))

    assert_completes(f)
    smalld.post.assert_called_once_with(POST_MESSAGE_ROUTE, {"content": "prompt: "})


def test_sends_prompts_without_buffering(make_subject, smalld):
    result1, result2 = None, None

    @click.command()
    def command():
        nonlocal result1, result2
        click.echo("echo 1")
        result1 = click.prompt("prompt 1")
        result2 = click.prompt("prompt 2")
        click.echo("echo 2")

    subject = make_subject(command)

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


def test_drops_conversation_when_timed_out(make_subject):
    @click.command()
    def command():
        click.prompt("prompt")

    subject = make_subject(command, timeout=0.2)
    f = subject.on_message(make_message("command"))

    assert_completes(f)
    assert not subject.pending


def test_prompts_in_DM_for_hidden_prompts(make_subject, smalld):
    @click.command()
    def command():
        click.prompt("prompt", hide_input=True)

    subject = make_subject(command)
    subject.on_message(make_message("command"))
    time.sleep(0.2)

    assert smalld.post.called_with(POST_DM_MESSAGE_ROUTE, {"content": "prompt: "})


def test_only_responds_to_hidden_prompts_answers_in_DM(make_subject, smalld):
    result = None

    @click.command()
    def command():
        nonlocal result
        result = click.prompt("prompt", hide_input=True)

    subject = make_subject(command)

    f = subject.on_message(make_message("command"))
    time.sleep(0.2)
    subject.on_message(make_message("visible result"))
    subject.on_message(make_message("hidden result", channel_id=DM_CHANNEL_ID))

    assert_completes(f)
    assert result == "hidden result"


def test_continues_conversation_in_DM_after_hidden_prompt(make_subject, smalld):
    @click.command()
    def command():
        click.echo("echo 1")
        click.prompt("prompt", hide_input=True)
        click.echo("echo 2")

    subject = make_subject(command)

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


def test_patches_click_functions_in_context_only(smalld):
    from smalld_click.utils import echo, prompt, click_echo, click_prompt

    # sanity checks
    assert echo is not click_echo
    assert prompt is not click_prompt

    assert click.echo is click_echo
    assert click.prompt is click_prompt

    @click.command()
    def command():
        pass

    with SmallDCliRunner(smalld, command):
        assert click.echo is echo
        assert click.prompt is prompt

    assert click.echo is click_echo
    assert click.prompt is click_prompt


def test_sends_chunked_messages_not_exceeding_message_length_limit(
    make_subject, smalld
):
    @click.command()
    def command():
        click.echo("a" * 3000)

    subject = make_subject(command)
    f = subject.on_message(make_message("command"))

    assert_completes(f)
    assert smalld.post.call_count == 2
    smalld.post.assert_has_calls(
        [
            call(POST_MESSAGE_ROUTE, {"content": "a" * 2000}),
            call(POST_MESSAGE_ROUTE, {"content": "a" * 1000 + "\n"}),
        ]
    )


def test_message_is_latest_message_payload(make_subject):
    msg1, msg2 = None, None

    @click.command()
    def command():
        nonlocal msg1, msg2
        conv = get_conversation()
        msg1 = conv.message
        click.prompt("prompt")
        msg2 = conv.message

    subject = make_subject(command)

    f = subject.on_message(make_message("command"))
    time.sleep(0.2)
    subject.on_message(make_message("result"))

    assert_completes(f)
    assert msg1 is not msg2
    assert msg1["content"] == "command"
    assert msg2["content"] == "result"
