from rest_framework import serializers

from .models import Room, Beacon, Building


class BuildingSerializer(serializers.ModelSerializer):
    rooms = serializers.HyperlinkedRelatedField(many=True,
                                                read_only=True,
                                                view_name='room-detail')

    class Meta:
        model = Building
        fields = ('id', 'building_name', 'rooms')


class RoomSerializer(serializers.ModelSerializer):
    building = serializers.HyperlinkedRelatedField(many=False,
                                                   read_only=True,
                                                   view_name='building-detail')

    beacons = serializers.HyperlinkedRelatedField(many=True,
                                                  read_only=True,
                                                  view_name='beacon-detail')

    class Meta:
        model = Room
        fields = ('id', 'room_code', 'beacons', 'building')


class BeaconSerializer(serializers.ModelSerializer):
    room = serializers.HyperlinkedRelatedField(many=False, read_only=True, view_name='room-detail')

    class Meta:
        model = Beacon
        fields = ('id', 'uuid', 'major', 'minor', 'room')
