from rest_framework import status
from rest_framework.exceptions import APIException


class AlreadyExists(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Conflict'
    default_code = 'already_exists'
