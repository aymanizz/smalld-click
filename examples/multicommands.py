import click

from smalld import SmallD
from smalld_click import SmallDCliRunner


# commands will be attached to this group.
# disable the help option, in order to disallow invoking the command with `++--help`.
@click.group(add_help_option=False)
def cli():
    # can be used to run some code before the subcommands run.
    pass


# command replacement for the default help option.
# we don't want the help command to have a help option as well.
@cli.command(add_help_option=False)
def help():
    """Show this message and exit."""
    click.echo(click.get_current_context().parent.get_help())


@cli.command()
@click.argument("name")
def greet(name):
    """Greet NAME."""
    click.echo("Hello %s!" % name)


@cli.command()
@click.argument("message", nargs=-1)
def echo(message):
    """Display MESSAGE."""
    click.echo(" ".join(message))


smalld = SmallD()

with SmallDCliRunner(smalld, cli, prefix="++", name=""):
    smalld.run()
