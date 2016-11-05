import requests
from django.db import transaction
from rest_framework import viewsets
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth.models import User
from .models import Room, Beacon, Building, Student
from .serializers import RoomSerializer, BeaconSerializer, BuildingSerializer, StudentDeserializer


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
    queryset = Student.objects.all()
    serializer_class = StudentDeserializer

    def create(self, request, format=None):
        serializer = StudentDeserializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.data

        r = requests.post("https://frontdoor.spa.gla.ac.uk/spacett/login.m",
                          data={'guid': data['username'], 'password': data['password']})

        if not r.status_code == requests.codes.ok:
            raise AuthenticationFailed("Wrong username or password")

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
            
            token = Token.objects.create(user=student.user)

        return Response({'token': token.key})
