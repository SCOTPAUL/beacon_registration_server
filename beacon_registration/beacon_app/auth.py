from datetime import timedelta, datetime

import pytz
from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token


# Modified from
# http://stackoverflow.com/questions/14567586/token-authentication-for-restful-api-should-the-token-be-periodically-changed
class ExpiringTokenAuthentication(TokenAuthentication):
    """
    Same as TokenAuthentication, except that Tokens become invalid a period of time after they have been generated.
    The time to expire should be set as a dictionary field mapping from 'TOKEN_EXPIRATION' to a datetime.timedelta
    in the REST_FRAMEWORK dictionary in settings.py
    """

    def authenticate_credentials(self, key):
        model = self.get_model()

        try:
            token = model.objects.select_related('user').get(key=key)
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token')

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted')

        if token_expired(token):
            raise exceptions.AuthenticationFailed('Token has expired')

        return token.user, token


def token_expired(token: Token) -> bool:
    # This is required for the time comparison
    utc_now = datetime.utcnow()
    utc_now = utc_now.replace(tzinfo=pytz.utc)

    delta = settings.REST_FRAMEWORK['TOKEN_EXPIRATION']

    return token.created < utc_now - delta
