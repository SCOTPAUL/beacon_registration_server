import calendar
import datetime

import requests
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import status
from rest_framework import viewsets, mixins
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed, NotFound, ParseError, NotAuthenticated
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from .auth import ExpiringTokenAuthentication
from .meetingbuilder import get_or_create_meetings
from .models import Room, Beacon, Building, Student, Class, Meeting, MeetingInstance, AttendanceRecord
from .permissions import IsUser
from .serializers import RoomSerializer, BeaconSerializer, BuildingSerializer, StudentDeserializer, ClassSerializer, \
    MeetingSerializer, StudentSerializer, MeetingInstanceSerializer, TimetableSerializer, AttendanceRecordSerializer, \
    BeaconDeserializer, FriendSerializer, FriendDeserializer, AllowedTimetableSerializer


class RoomViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class BeaconViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Beacon.objects.all()
    serializer_class = BeaconSerializer


class BuildingViewSet(viewsets.ReadOnlyModelViewSet):
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

        new_timetable_json = None

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

        try:
            student = Student.objects.get(user__username=data['username'])
        except Student.DoesNotExist:
            user = User.objects.create_user(username=data['username'])
            student = Student.objects.create(user=user)

        with transaction.atomic():
            try:
                token = Token.objects.get(user=student.user)
                token.delete()
            except Token.DoesNotExist:
                pass

            if new_timetable_json is not None:
                get_or_create_meetings(new_timetable_json, student)

            token = Token.objects.create(user=student.user)

        return Response({'token': token.key})


class ClassViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Class.objects.all()
    serializer_class = ClassSerializer


class MeetingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Meeting.objects.all()
    serializer_class = MeetingSerializer


class MeetingInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MeetingInstance.objects.all()
    serializer_class = MeetingInstanceSerializer


class StudentViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    lookup_field = 'user__username'
    authentication_classes = (ExpiringTokenAuthentication,)
    permission_classes = (IsUser,)


class FriendViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.CreateModelMixin, mixins.DestroyModelMixin):
    authentication_classes = (ExpiringTokenAuthentication,)
    serializer_class = FriendSerializer
    permission_classes = (IsAuthenticated,)
    lookup_field = 'user__username'

    def create(self, request, *args, **kwargs):
        student = self.get_queryset()[0]

        serializer = FriendDeserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_share_username = serializer.validated_data

        share_student = Student.objects.get(user__username=new_share_username['username'])

        if share_student == student:
            raise ParseError(detail="Can't add self as a friend")

        student.shared_with.add(share_student)
        student.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        student = self.get_queryset()[0]

        remove_share_username = kwargs['user__username']

        try:
            share_student = Student.objects.get(user__username=remove_share_username)
        except Student.DoesNotExist:
            raise NotFound(detail="Can't remove, no such friend")

        if share_student == student:
            raise ParseError(detail="Can't remove self")

        if not student.shared_with.filter(user__username=share_student.user.username).exists():
            raise NotFound(detail="Can't remove, no such friend")

        student.shared_with.remove(share_student)
        student.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_queryset(self):
        return Student.objects.filter(user=self.request.user)


class TimetableViewSet(viewsets.ViewSet):
    """
    Contains the views which present MeetingInstance information in a
    client friendly manner
    """
    authentication_classes = (ExpiringTokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    lookup_field = 'username'

    def list(self, request, format=None):
        student = self.request.user.student

        return Response(AllowedTimetableSerializer(student, context={'request': request}).data)

    def retrieve(self, request, username=None, format=None):
        student = self.request.user.student
        timetable_username = username

        try:
            timetable_student = Student.objects.get(user__username=timetable_username)
        except Student.DoesNotExist:
            raise NotAuthenticated(detail="You do not have permission to view this timetable")

        if timetable_student == student or student.shared_from.filter(pk=timetable_student.pk).exists():
            return Response(
                TimetableSerializer(self.get_meetings(timetable_student), many=True, context={'student': student, 'request':request}).data)
        raise NotAuthenticated(detail="You do not have permission to view this timetable")

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

        record = AttendanceRecord.objects.get_or_create(student=student, meeting_instance=meeting_instance)[0]

        return Response(AttendanceRecordSerializer(record, context={'request': request}).data,
                        status=status.HTTP_201_CREATED)
