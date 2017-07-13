import pytz
import requests
from django.db import transaction
from requests import Session
from rest_framework import status
from rest_framework import viewsets, mixins
from rest_framework.authtoken.models import Token
from rest_framework.decorators import detail_route, list_route, api_view, permission_classes
from rest_framework.exceptions import AuthenticationFailed, NotFound, ParseError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.reverse import reverse
from django.conf import settings
from rest_framework.utils.serializer_helpers import ReturnDict

from beacon_app.exceptions import AlreadyExists

from .crypto import PasswordCrypto
from .auth import ExpiringTokenAuthentication, token_expired
from .meetingbuilder import get_or_create_meetings
from .permissions import IsUser, IsUserOrSharedWithUser, IsAuthenticatedOrCreating
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


class AccountsViewSet(viewsets.ViewSet):
    """
    Contains the views for accounts
    """
    permission_classes = (IsAuthenticatedOrCreating,)
    authentication_classes = (ExpiringTokenAuthentication,)

    def create(self, request, *args, **kwargs):
        username = request.data.get('username', None)
        if username and Student.objects.filter(user__username=username).exists():
            raise AlreadyExists(detail="Account with this username already exists")

        serializer = NewAccountDeserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_account_details = serializer.data

        with requests.Session() as s:
            r = s.post("https://frontdoor.spa.gla.ac.uk/spacett/login.m",
                       data={'guid': new_account_details['username'], 'password': new_account_details['password']})

            if not r.status_code == requests.codes.ok:
                raise AuthenticationFailed("Wrong username or password")
            else:
                user = User.objects.create_user(username=new_account_details['username'],
                                                password=new_account_details['password'])
                student = Student.objects.create(user=user, nickname=new_account_details['nickname'])

                try:
                    token = Token.objects.get(user=student.user)
                    if token_expired(token):
                        token.delete()
                        token = make_token(new_account_details, student, session=s)

                except Token.DoesNotExist:
                    token = make_token(new_account_details, student, session=s)

                return Response({'auth_token': PasswordCrypto(user).encrypt(new_account_details['password']),
                                 'session_token': token.key})

    @list_route(methods=['POST', 'GET'], url_path='nickname')
    def nickname(self, request, *args, **kwargs):
        student = self.get_object()

        if request.method == 'POST':
            if request.data.get('nickname', None) == student.nickname:
                return Response(SimpleStudentSerializer(student).data, status=status.HTTP_200_OK)

            serializer = NicknameChangeSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            new_nickname = serializer.data['nickname']
            student.nickname = new_nickname
            student.save()

            return Response(SimpleStudentSerializer(student).data, status=status.HTTP_200_OK)

        elif request.method == 'GET':
            return Response({'nickname': student.nickname})

    def get_object(self):
        return self.request.user.student

    @list_route(methods=['POST'], url_path='make-auth-token', permission_classes=(AllowAny,))
    def make_auth_token(self, request, *args, **kwargs):
        serializer = AuthTokenRequestDeserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.data

        try:
            student = Student.objects.get(user__username=data['username'])
        except Student.DoesNotExist:
            raise NotFound("No such student exists")

        return Response({'auth_token': PasswordCrypto(student.user).encrypt(data['password'])})


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
            raise NotFound("No such student exists")

        auth_token = data['auth_token']
        data['password'] = PasswordCrypto(student.user).decrypt(auth_token)

        try:
            token = Token.objects.get(user=student.user)
            if token_expired(token):
                token.delete()
                token = make_token(data, student)
            else:
                if not student.fake_account:
                    with requests.Session() as s:
                        r = s.post("https://frontdoor.spa.gla.ac.uk/spacett/login.m",
                                   data={'guid': data['username'], 'password': data['password']})

                        if not r.status_code == requests.codes.ok:
                            raise AuthenticationFailed("Wrong username or password")

        except Token.DoesNotExist:
            token = make_token(data, student)

        return Response({'token': token.key})


def do_sync(session: Session, student: Student):
    next_year = datetime.datetime.utcnow() + datetime.timedelta(days=365)
    next_year_timestamp = calendar.timegm(next_year.utctimetuple())

    r = session.get("https://frontdoor.spa.gla.ac.uk/spacett/timetable/events.m",
                    params={'start': 0, 'end': next_year_timestamp})

    new_timetable_json = r.json()

    if new_timetable_json is not None:
        get_or_create_meetings(new_timetable_json, student)


def make_token(data: ReturnDict, student: Student, session: Session=None) -> Token:
    token = Token.objects.create(user=student.user)

    if student.fake_account:
        return token

    if session:
        do_sync(session, student)
    else:
        with requests.Session() as session:
            r = session.post("https://frontdoor.spa.gla.ac.uk/spacett/login.m",
                             data={'guid': data['username'], 'password': data['password']})

            if not r.status_code == requests.codes.ok:
                raise AuthenticationFailed("Wrong username or password")

            do_sync(session, student)

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
        :return: list of student friend GUIDs and nicknames who attended event
        """
        friends = request.user.student.friends
        attended = friends.filter(attendance_records__meeting_instance__pk=pk)

        return Response(SimpleStudentSerializer(attended, many=True).data)


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

        return Response(SimpleStudentSerializer(student.friends, many=True).data)

    @detail_route(methods=['GET'], url_path='current-location')
    def current_location(self, request, *args, **kwargs):
        user__username = kwargs['user__username']
        try:
            friend = Student.objects.get(user__username=user__username)
        except Student.DoesNotExist:
            raise NotFound("No such friend {}".format(user__username))

        if not IsUserOrSharedWithUser().has_object_permission(request, self, friend):
            raise NotFound("No such friend {}".format(user__username))

        data = Student.objects.get(user__username=user__username).location

        if data['meeting_instance'] is None:
            data.pop('meeting_instance')
        else:
            meeting_inst = data['meeting_instance']
            data['time_start'] = meeting_inst.meeting.time_start
            data['time_end'] = meeting_inst.time_end
            data['room'] = meeting_inst.meeting.room.name
            data['building'] = meeting_inst.meeting.room.building.name
            data['class_name'] = str(meeting_inst.meeting.class_rel)

        serializer = LocationSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        return Response(serializer.data)

    @list_route(methods=['GET'], url_path='location-statuses')
    def location_statuses(self, *args, **kwargs):
        student = self.get_object()
        serializer = LocationStatusSerializer(student.friends, many=True)
        return Response(serializer.data)

    @list_route(methods=['GET'], permission_classes=(IsAuthenticated,), url_path='friendship-statuses-involving-me')
    def list_friendships_involving_me(self, *args, **kwargs):
        student = self.get_object()

        response = {'friend_requests': [], 'friends': []}
        for friendship in Friendship.objects.filter(Q(initiating_student=student) | Q(receiving_student=student)):
            if not friendship.accepted and friendship.receiving_student == student:
                response['friend_requests'].append(friendship.initiating_student if friendship.receiving_student == student
                                                   else friendship.receiving_student)
            elif friendship.accepted:
                response['friends'].append(friendship.initiating_student if friendship.receiving_student == student
                                           else friendship.receiving_student)

        serializer = FriendsSerializer(response)

        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        student = self.get_object()

        serializer = FriendDeserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_friend_username = serializer.validated_data

        try:
            new_friend = Student.objects.get(user__username=new_friend_username['username'])
        except Student.DoesNotExist:
            raise NotFound("No such student exists")

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

    @list_route(methods=['POST'], url_path='add-multiple')
    def create_multiple(self, request, format=None):
        student = self.request.user.student
        
        serializer = BeaconSightingDeserializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        beacon_sightings = serializer.data
        new_attendance_records = []

        for sighting in beacon_sightings:
            try:
                beacon = Beacon.objects.get(uuid=sighting['uuid'], major=sighting['major'], minor=sighting['minor'])
            except Beacon.DoesNotExist:
                continue

            try:
                seen_at_date = sighting['seen_at_time'].date()
                seen_at_time = sighting['seen_at_time'].time()

                meeting_instance = MeetingInstance.objects.get(room=beacon.room,
                                                               date=seen_at_date,
                                                               meeting__time_start__lte=seen_at_time,
                                                               meeting__time_end__gte=seen_at_time,
                                                               meeting__students=student)
            except MeetingInstance.DoesNotExist:
                continue

            try:
                AttendanceRecord.objects.get(student=student, meeting_instance=meeting_instance)
            except AttendanceRecord.DoesNotExist:
                record = AttendanceRecord.objects.create(student=student, meeting_instance=meeting_instance,
                                                         time_attended=sighting['seen_at_time'])

                new_attendance_records.append(record)

        return Response(AttendanceRecordSerializer(new_attendance_records, many=True).data)

    def create(self, request, format=None):
        student = self.request.user.student

        serializer = BeaconSightingDeserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            # TODO: Replace this lookup with a ShuffledIDs lookup
            beacon = Beacon.objects.get(uuid=data['uuid'], major=data['major'], minor=data['minor'])
        except Beacon.DoesNotExist:
            raise NotFound("No such beacon exists")

        try:
            seen_at_date = data['seen_at_time'].date()
            seen_at_time = data['seen_at_time'].time()

            meeting_instance = MeetingInstance.objects.get(room=beacon.room,
                                                           date=seen_at_date,
                                                           meeting__time_start__lte=seen_at_time,
                                                           meeting__time_end__gte=seen_at_time,
                                                           meeting__students=student)
        except MeetingInstance.DoesNotExist:
            raise NotFound("The student is not in a class where this beacon is")

        try:
            AttendanceRecord.objects.get(student=student, meeting_instance=meeting_instance)
            raise AlreadyExists("This attendance record already exists")
        except AttendanceRecord.DoesNotExist:
            record = AttendanceRecord.objects.create(student=student, meeting_instance=meeting_instance,
                                                     time_attended=data['seen_at_time'])

        return Response(AttendanceRecordSerializer(record).data,
                        status=status.HTTP_201_CREATED)

    @detail_route(methods=['POST'], url_path='force-creation')
    def force_record_creation(self, request, format=None, pk=None):
        tz = pytz.timezone(settings.TIME_ZONE)

        student = self.request.user.student

        if pk is None:
            raise ParseError("No meeting instance pk included with request")

        try:
            meeting_instance = MeetingInstance.objects.get(pk=pk)
            if AttendanceRecord.objects.filter(student=student,
                                               meeting_instance=meeting_instance).exists():
                raise AlreadyExists("You have already attended this meeting instance")
            else:
                attended_at = datetime.datetime.combine(meeting_instance.date, meeting_instance.meeting.time_start)

                record = AttendanceRecord.objects.create(student=student, meeting_instance=meeting_instance,
                                                         time_attended=attended_at.replace(tzinfo=tz),
                                                         manually_created=True)

                return Response(AttendanceRecordSerializer(record).data,
                                status=status.HTTP_201_CREATED)

        except MeetingInstance.DoesNotExist:
            raise NotFound("No such meeting instance exists")


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


class LogEntryViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated,)
    authentication_classes = (ExpiringTokenAuthentication,)

    @transaction.atomic()
    @list_route(methods=['POST'], url_path='log-multiple')
    def log_multiple(self, request, format=None):
        student = self.get_object()

        serializer = LogEntryDeserializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        logs = serializer.data

        for log in logs:
            LogEntry.objects.create(event_type=log['event_type'], event_text=log['event_text'],
                                    timestamp=log['timestamp'], student=student)

        return Response(status=status.HTTP_201_CREATED)

    def get_object(self):
        return self.request.user.student
