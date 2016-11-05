from rest_framework import serializers

from .models import Room, Beacon, Building, Class, Meeting, Student


class BuildingSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Building
        fields = ('id', 'building_name', 'rooms')


class RoomSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Room
        fields = ('id', 'room_code', 'beacons', 'building')


class BeaconSerializer(serializers.HyperlinkedModelSerializer):
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


class MeetingSerializer(serializers.HyperlinkedModelSerializer):
    day_of_week = serializers.CharField(source='weekday')

    class Meta:
        model = Meeting
        fields = ('time_start', 'time_end', 'day_of_week', 'date_start', 'date_end', 'room', 'class_rel')


class ClassSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Class
        fields = ('class_code', 'meetings')


class StudentSerializer(serializers.HyperlinkedModelSerializer):
    username = serializers.CharField(source='user.username')

    class Meta:
        model = Student
        fields = ('username', 'classes')
