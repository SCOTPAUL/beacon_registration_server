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
