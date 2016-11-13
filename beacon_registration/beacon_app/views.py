import calendar
import datetime

import requests
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import viewsets, mixins
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .meetingbuilder import get_or_create_meetings
from .auth import ExpiringTokenAuthentication
from .models import Room, Beacon, Building, Student, Class, Meeting
from .permissions import IsUser
from .serializers import RoomSerializer, BeaconSerializer, BuildingSerializer, StudentDeserializer, ClassSerializer, \
    MeetingSerializer, StudentSerializer


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


class StudentViewSet(viewsets.GenericViewSet, mixins.RetrieveModelMixin):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    lookup_field = 'user__username'
    authentication_classes = (ExpiringTokenAuthentication,)
    permission_classes = (IsUser,)
