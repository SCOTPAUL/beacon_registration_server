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


class StudentDeserializer(serializers.Serializer):
    username = serializers.CharField(max_length=140, required=True)
    password = serializers.CharField(required=True)

    @staticmethod
    def validate_username(value: str) -> str:
        if not len(value) > 0:
            raise serializers.ValidationError("Username cannot be empty")

        if not (value[:-1].isdigit() and value[-1].isalpha()):
            raise serializers.ValidationError("Username not in correct format")

        return value
