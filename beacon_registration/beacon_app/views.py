from rest_framework import viewsets

from .models import Room, Beacon, Building
from .serializers import RoomSerializer, BeaconSerializer, BuildingSerializer


class RoomViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class BeaconViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Beacon.objects.all()
    serializer_class = BeaconSerializer


class BuildingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer
