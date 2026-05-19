"""Public observability helpers for MIRASTACK agent authors.

Use :func:`start_action` as a context manager to wrap each action handler
with a uniform span + metric pair.

Example::

    from mirastack_sdk.obs import start_action

    def handle_action(req):
        with start_action("query_metrics", "rate") as span:
            span.set_attribute("custom.attr", "value")
            ...
"""

from mirastack_sdk.obs.obs import ActionSpan, start_action

__all__ = ["ActionSpan", "start_action"]
