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
