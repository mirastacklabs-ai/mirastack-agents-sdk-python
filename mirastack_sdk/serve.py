"""gRPC server bootstrap for MIRASTACK plugins.

Usage::

    from mirastack_sdk import Plugin, serve

    class MyPlugin(Plugin):
        ...

    if __name__ == "__main__":
        serve(MyPlugin())
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from concurrent import futures

import grpc

from mirastack_sdk.plugin import Plugin

logger = logging.getLogger("mirastack_sdk")


def serve(plugin: Plugin, *, max_workers: int = 10) -> None:
    """Start the plugin gRPC server and block until shutdown.

    This is the main entry point for plugin processes.
    The engine launches plugin processes and communicates via gRPC.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    info = plugin.info()
    if info is None:
        logger.fatal("plugin.info() must not return None")
        sys.exit(1)

    listen_addr = os.environ.get("MIRASTACK_PLUGIN_ADDR", "[::]:0")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))

    # TODO(phase-2): Register PluginService implementation that delegates to `plugin`

    port = server.add_insecure_port(listen_addr)

    # Write the actual port to stdout for the engine to discover
    print(f"MIRASTACK_PLUGIN_PORT={port}", flush=True)

    server.start()

    logger.info("Plugin serving: %s v%s on port %d", info.name, info.version, port)

    # Handle shutdown signals
    shutdown_event = asyncio.Event()

    def _signal_handler(sig: int, frame: object) -> None:
        logger.info("Shutting down plugin (signal %d)", sig)
        shutdown_event.set()
        server.stop(grace=5)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    server.wait_for_termination()
