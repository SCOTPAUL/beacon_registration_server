from rest_framework import permissions


class IsUser(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has a `user` attribute.
    """

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class IsUserOrSharedWithUser(permissions.BasePermission):
    """
    Object-level permission to only allow owners or users that the owner has shared with to view it
    """

    def has_object_permission(self, request, view, obj):
        authed_student = request.user.student
        requested_student = obj

        return authed_student == requested_student or authed_student.friends.filter(
            pk=requested_student.pk).exists()


# Based on https://github.com/encode/django-rest-framework/issues/1067
class IsAuthenticatedOrCreating(permissions.BasePermission):
    """
    Allows access if the user is already authenticated or they are trying to invoke a ViewSet's create method
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated():
            return view.action == 'create'

        return True
