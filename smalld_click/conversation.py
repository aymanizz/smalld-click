import io

import click

click_prompt = click.prompt
click_echo = click.echo


class Conversation:
    def __init__(self, runner, message, timeout):
        self.runner = runner
        self.smalld = runner.smalld
        self.message = message
        self.timeout = timeout
        self.channel_id = message["channel_id"]
        self.user_id = message["author"]["id"]
        self.echo_buffer = io.StringIO()
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
        self.echo_buffer = io.StringIO()
        if not content.strip():
            return

        smalld, channel_id = self.runner.smalld, self.channel_id
        smalld.post(f"/channels/{channel_id}/messages", {"content": content})

    def wait_for_message(self):
        handle = self.runner.add_listener(self.user_id, self.channel_id)
        if handle.wait(self.timeout):
            self.message = handle.result
            return handle.result["content"]
        else:
            self.runner.remove_listener(self.user_id, self.channel_id)
            raise TimeoutError("timed out while waiting for user response")

    def close(self):
        self.__exit__(None, None, None)
        click.get_current_context().abort()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.flush()


def get_conversation():
    return click.get_current_context().find_object(Conversation)
