"""Account-status enforcement (blueprint §5.2, §8.2).

A session that belongs to an account that is no longer active is destroyed on
the next request, so disabling an account also ends any live session.
"""
import logging

from django.contrib.auth import logout

log = logging.getLogger("compass.security")


class AccountStatusMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not user.is_account_active():
            log.info("session ended: account %s status=%s", user.pk, user.status)
            logout(request)
        return self.get_response(request)
