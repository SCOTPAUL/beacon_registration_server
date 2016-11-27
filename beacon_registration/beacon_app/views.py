import calendar
import datetime
from rest_framework import status
import requests
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import viewsets, mixins
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed, ValidationError, NotFound, ParseError
from rest_framework import serializers

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from .meetingbuilder import get_or_create_meetings
from .auth import ExpiringTokenAuthentication
from .models import Room, Beacon, Building, Student, Class, Meeting, MeetingInstance, AttendanceRecord
from .permissions import IsUser
from .serializers import RoomSerializer, BeaconSerializer, BuildingSerializer, StudentDeserializer, ClassSerializer, \
    MeetingSerializer, StudentSerializer, MeetingInstanceSerializer, TimetableSerializer


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


class TimetableViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    authentication_classes = (ExpiringTokenAuthentication,)
    permission_classes = (IsAuthenticated,)
    serializer_class = TimetableSerializer

    def get_queryset(self):
        meetings = self.request.user.student.meeting_set.all()

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

#class AttendanceRecordViewSet(viewsets.ViewSet):
#    permission_classes = (IsAuthenticated,)
#    queryset = AttendanceRecord.objects.all()
#    serializer_class = StudentDeserializer

#    def create(self, request, format=None):