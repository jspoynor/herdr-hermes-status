"""Native Hermes plugin: explicit setup/status/rollback, no import-time writes."""
from .management import add_arguments, handle


def register(ctx):
    ctx.register_cli_command(
        name='herdr',
        help='Set up or inspect Herdr agent status on this machine',
        setup_fn=add_arguments,
        handler_fn=handle,
    )
