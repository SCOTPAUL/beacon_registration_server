import requests
from django.db import transaction
from rest_framework import status
from rest_framework import viewsets, mixins
from rest_framework.authtoken.models import Token
from rest_framework.decorators import detail_route, list_route
from rest_framework.exceptions import AuthenticationFailed, NotFound, ParseError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.reverse import reverse
from django.conf import settings
from rest_framework.utils.serializer_helpers import ReturnDict

from beacon_app.exceptions import AlreadyExists
from .auth import ExpiringTokenAuthentication, token_expired
from .meetingbuilder import get_or_create_meetings
from .permissions import IsUser, IsUserOrSharedWithUser
from .serializers import *
from .models import *


class RoomViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = ()
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class BeaconViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = ()
    queryset = Beacon.objects.all()
    serializer_class = BeaconSerializer


class BuildingViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = ()
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer


class TokenViewSet(viewsets.ViewSet):
    """
    Contains the views for exchanging username and password information for a temporary access token
    """
    permission_classes = (AllowAny,)
    queryset = Token.objects.all()
    serializer_class = StudentDeserializer

    def create(self, request, format=None):
        serializer = StudentDeserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.data

        try:
            student = Student.objects.get(user__username=data['username'])
        except Student.DoesNotExist:
            user = User.objects.create_user(username=data['username'])
            student = Student.objects.create(user=user)

        try:
            with requests.Session() as s:
                r = s.post("https://frontdoor.spa.gla.ac.uk/spacett/login.m",
                           data={'guid': data['username'], 'password': data['password']})

                if not r.status_code == requests.codes.ok:
                    raise AuthenticationFailed("Wrong username or password")

            token = Token.objects.get(user=student.user)
            if token_expired(token):
                token.delete()
                token = self.make_token(data, student)
            else:
                with requests.Session() as s:
                    r = s.post("https://frontdoor.spa.gla.ac.uk/spacett/login.m",
                               data={'guid': data['username'], 'password': data['password']})

                    if not r.status_code == requests.codes.ok:
                        raise AuthenticationFailed("Wrong username or password")

        except Token.DoesNotExist:
            token = self.make_token(data, student)

        return Response({'token': token.key})

    @staticmethod
    def make_token(data: ReturnDict, student: Student) -> Token:
        token = Token.objects.create(user=student.user)

        with requests.Session() as s:
            r = s.post("https://frontdoor.spa.gla.ac.uk/spacett/login.m",
                       data={'guid': data['username'], 'password': data['password']})

            if not r.status_code == requests.codes.ok:
                raise AuthenticationFailed("Wrong username or password")

            next_year = datetime.datetime.utcnow() + datetime.timedelta(days=365)
            next_year_timestamp = calendar.timegm(next_year.utctimetuple())

            r = s.get("https://frontdoor.spa.gla.ac.uk/spacett/timetable/events.m",
                      params={'start': 0, 'end': next_year_timestamp})

            new_timetable_json = r.json()

            if new_timetable_json is not None:
                get_or_create_meetings(new_timetable_json, student)

        return token


class ClassViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = ()
    queryset = Class.objects.all()
    serializer_class = ClassSerializer


class MeetingViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = ()
    queryset = Meeting.objects.all()
    serializer_class = MeetingSerializer


class MeetingInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = (ExpiringTokenAuthentication,)
    queryset = MeetingInstance.objects.all()
    serializer_class = MeetingInstanceSerializer
    lookup_field = 'pk'

    @detail_route(methods=['get'], permission_classes=(IsAuthenticated,), url_path='friends-attended')
    def list_attended_friends(self, request, pk, format=None):
        """
        :return: list of student friend GUIDs who attended event
        """
        shared_from = request.user.student.shared_from
        attended = shared_from.filter(attendance_records__meeting_instance__pk=pk)

        return Response([str(student) for student in attended])


class StudentViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    lookup_field = 'user__username'
    authentication_classes = (ExpiringTokenAuthentication,)
    permission_classes = (IsAuthenticated, IsUser)


class FriendViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin):
    authentication_classes = (ExpiringTokenAuthentication,)
    serializer_class = FriendshipSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = 'user__username'

    def list(self, request, *args, **kwargs):
        student = self.get_object()

        friends = []
        friendships = student.friendships
        for friendship in friendships:
            if friendship.initiating_student == student:
                friends.append(friendship.receiving_student.user.username)
            else:
                friends.append(friendship.initiating_student.user.username)

        return Response(friends)

    @list_route(methods=['get'], permission_classes=(IsAuthenticated,), url_path='friendship-statuses-involving-me')
    def list_friendships_involving_me(self, *args, **kwargs):
        student = self.get_object()

        return Response(FriendshipSerializer(Friendship.objects.filter(
            Q(initiating_student=student) | Q(receiving_student=student)), many=True).data)

    def create(self, request, *args, **kwargs):
        student = self.get_object()

        serializer = FriendDeserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_friend_username = serializer.validated_data
        new_friend = Student.objects.get(user__username=new_friend_username['username'])

        if new_friend == student:
            raise ParseError(detail="Can't add self as a friend")

        if Friendship.objects.filter(initiating_student=student, receiving_student=new_friend).exists():
            raise AlreadyExists(detail="You have already sent a friend request to this user")

        try:
            friendship = Friendship.objects.get(receiving_student=student, initiating_student=new_friend)
            friendship.accepted = True
            friendship.save()
            return Response(FriendshipSerializer(friendship).data, status=status.HTTP_200_OK)
        except Friendship.DoesNotExist:
            friendship = Friendship.objects.create(initiating_student=student, receiving_student=new_friend)
            return Response(FriendshipSerializer(friendship).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        student = self.get_object()

        removed_friend_username = kwargs['user__username']

        try:
            friend_to_remove = Student.objects.get(user__username=removed_friend_username)
        except Student.DoesNotExist:
            raise NotFound(detail="Can't remove, no such friend")

        if friend_to_remove == student:
            raise ParseError(detail="Can't remove self")

        try:
            friendship = Friendship.objects.get(initiating_student=student, receiving_student=friend_to_remove)
        except Friendship.DoesNotExist:
            try:
                friendship = Friendship.objects.get(receiving_student=student, initiating_student=friend_to_remove)
            except Friendship.DoesNotExist:
                raise NotFound(detail="Can't remove, no such friend")

        friendship.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_object(self):
        return self.request.user.student


def viewable_students(request: Request, view_base, format=None) -> Response:
    """
    A generic view for listing which resources are accessible by the Student sending this request
    :param view_base: the base_name of the view to use for the lookup
    :param request: the Request provided to the calling view
    :param format: the format of the response
    :return: a Response showing which resources of this type are available
    """
    student = request.user.student
    return Response(AllowedTimetableSerializer(student, base_view=view_base, context={'request': request}).data)


class TimetableViewSet(viewsets.ViewSet):
    """
    Contains the views which present MeetingInstance information in a
    client friendly manner
    """
    authentication_classes = (ExpiringTokenAuthentication,)
    permission_classes = (IsAuthenticated, IsUserOrSharedWithUser)
    lookup_field = 'username'

    def get_object(self, username: str) -> Student:
        obj = get_object_or_404(Student, user__username=username)
        self.check_object_permissions(self.request, obj)
        return obj

    def list(self, request, format=None):
        return viewable_students(request, 'timetable', format)

    def retrieve(self, request, username=None, format=None):
        timetable_username = username
        timetable_student = self.get_object(timetable_username)
        return Response(TimetableSerializer(self.get_meetings(timetable_student), many=True,
                                            context={'student': timetable_student, 'request': request}).data)

    def get_meetings(self, student: Student):
        meetings = student.meeting_set.all()

        queryset = MeetingInstance.objects.filter(meeting__in=meetings)

        day = self.request.query_params.get('day', None)
        week = self.request.query_params.get('week', None)
        month = self.request.query_params.get('month', None)

        try:
            if day is not None:
                day_date = datetime.datetime.strptime(day, '%Y-%m-%d').date()
                return queryset.filter(date=day_date)
            elif week is not None:
                day_date = datetime.datetime.strptime(week, '%Y-%m-%d').date()
                week_start = day_date - datetime.timedelta(days=day_date.weekday())
                week_end = week_start + datetime.timedelta(days=6)
                return queryset.filter(date__gte=week_start, date__lte=week_end)
            elif month is not None:
                month_datetime = datetime.datetime.strptime(month, '%Y-%m')
                month = month_datetime.month
                year = month_datetime.year
                return queryset.filter(date__year=year, date__month=month)
            else:
                return queryset
        except ValueError:
            raise ParseError(detail="Filtering parameter was not in a valid format")


class AttendancePercentageViewSet(viewsets.ViewSet):
    authentication_classes = (ExpiringTokenAuthentication,)
    permission_classes = (IsAuthenticated, IsUserOrSharedWithUser)
    lookup_field = 'username'

    def get_object(self, username: str) -> Student:
        obj = get_object_or_404(Student, user__username=username)
        self.check_object_permissions(self.request, obj)
        return obj

    @staticmethod
    def list(request, format=None):
        return viewable_students(request, 'attendance', format)

    def retrieve(self, request, username=None, format=None):
        timetable_username = username
        timetable_student = self.get_object(timetable_username)

        urls_list = [
            {'class_name': str(k), 'url': reverse('class-detail', args=[k.pk], request=request), 'percentage': v} for
            k, v in timetable_student.attendances.items()]

        return Response(urls_list)


class AttendanceRecordViewSet(viewsets.ViewSet):
    """
    Contains the views related to creating AttendanceRecords
    """
    authentication_classes = (ExpiringTokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def create(self, request, format=None):
        student = self.request.user.student

        serializer = BeaconDeserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            # TODO: Replace this lookup with a ShuffledIDs lookup
            beacon = Beacon.objects.get(uuid=data['uuid'], major=data['major'], minor=data['minor'])
        except Beacon.DoesNotExist:
            raise NotFound("No such beacon exists")

        try:
            current_time = datetime.datetime.now().time()
            current_date = datetime.date.today()
            meeting_instance = MeetingInstance.objects.get(room=beacon.room, date=current_date,
                                                           meeting__time_start__lte=current_time,
                                                           meeting__time_end__gte=current_time,
                                                           meeting__students=student)
        except MeetingInstance.DoesNotExist:
            raise NotFound("The student is not in a class where this beacon is")

        record, created = AttendanceRecord.objects.get_or_create(student=student, meeting_instance=meeting_instance)
        if created:
            record.time_attended = datetime.datetime.now().time()
            record.save()

        return Response(AttendanceRecordSerializer(record, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)


class StreakViewSet(viewsets.ViewSet):
    authentication_classes = (ExpiringTokenAuthentication,)
    permission_classes = (IsAuthenticated, IsUserOrSharedWithUser)
    lookup_field = 'username'

    def get_object(self, username: str) -> Student:
        obj = get_object_or_404(Student, user__username=username)
        self.check_object_permissions(self.request, obj)
        return obj

    def list(self, request, format=None):
        return viewable_students(request, 'streak', format)

    def retrieve(self, request, username=None, format=None):
        timetable_username = username
        timetable_student = self.get_object(timetable_username)

        return Response(
            StreaksSerializer(timetable_student, context={'request': request, 'student': timetable_student}).data)


class SourceViewSet(viewsets.ViewSet):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def list(self, request, format=None):
        if settings.SOURCE_CODE_URL:
            return Response("Source code and license available at: " + settings.SOURCE_CODE_URL)
        else:
            return Response("There seems to be a configuration error. Please contact the developer at "
                            "paul.cowie@ntlworld.com")
