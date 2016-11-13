from rest_framework import serializers

from .models import Room, Beacon, Building, Class, Meeting, Student, MeetingInstance


class BuildingSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Building
        fields = ('building_name', 'rooms')


class RoomSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Room
        fields = ('room_code', 'beacons', 'building')


class BeaconSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Beacon
        fields = ('uuid', 'major', 'minor', 'room')


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


class ReservedNameHyperlinkedModelSerializer(serializers.HyperlinkedModelSerializer):
    """Allows the usage of reserved fieldnames by appending a '_' to the field name in a subclass"""

    def __init__(self, *args, **kwargs):
        super(ReservedNameHyperlinkedModelSerializer, self).__init__(*args, **kwargs)

        fields = self.fields

        for field_name in fields:
            if field_name.endswith("_"):
                fields[field_name[:-1]] = fields.pop(field_name)

class MeetingInstanceSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = MeetingInstance
        fields = ('room', 'date')

class MeetingSerializer(ReservedNameHyperlinkedModelSerializer):
    instances = MeetingInstanceSerializer(many=True, read_only=True)
    day_of_week = serializers.CharField(source='weekday')
    class_ = serializers.HyperlinkedRelatedField(source='class_rel', view_name='class-detail', many=False,
                                                 read_only=True)

    class Meta:
        model = Meeting
        fields = ('time_start', 'time_end', 'day_of_week', 'class_', 'instances')




class ClassSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Class
        fields = ('class_code', 'meetings')


class StudentSerializer(serializers.HyperlinkedModelSerializer):
    username = serializers.CharField(source='user.username')

    class Meta:
        model = Student
        fields = ('username', 'classes')
