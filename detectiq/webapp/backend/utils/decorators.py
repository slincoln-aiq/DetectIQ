from asyncio import get_event_loop, new_event_loop, set_event_loop
from functools import wraps

from asgiref.sync import async_to_sync
from rest_framework.decorators import action

from detectiq.core.utils.logging import get_logger

logger = get_logger(__name__)


def async_action(detail=False, methods=None, url_path=None):
    """Decorator to handle async actions in DRF viewsets."""

    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            try:
                loop = get_event_loop()
            except RuntimeError:
                # If there's no event loop in the current thread, create one
                loop = new_event_loop()
                set_event_loop(loop)

            return loop.run_until_complete(func(*args, **kwargs))

        # Preserve DRF action decorator attributes
        wrapped.detail = detail  # type: ignore
        wrapped.methods = methods or ["GET"]  # type: ignore
        wrapped.url_path = url_path  # type: ignore
        wrapped.kwargs = {  # type: ignore
            "detail": detail,
            "methods": methods or ["GET"],
            "url_path": url_path,
        }

        return wrapped

    return decorator