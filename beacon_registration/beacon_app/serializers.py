import dateutil.parser
from rest_framework import serializers

from .utils import Streak
from .models import Room, Beacon, Building, Class, Meeting, Student, MeetingInstance, AttendanceRecord


class BuildingSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Building
        fields = ('name', 'rooms')


class RoomSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Room
        fields = ('room_code', 'beacons', 'building')


class BeaconSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Beacon
        fields = ('uuid', 'major', 'minor', 'room')


class BeaconDeserializer(serializers.Serializer):
    uuid = serializers.UUIDField(required=True)
    major = serializers.IntegerField(required=True)
    minor = serializers.IntegerField(required=True)


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


class FriendDeserializer(serializers.Serializer):
    username = serializers.CharField(max_length=140, required=True)

    @staticmethod
    def validate_username(value: str) -> str:
        if not Student.objects.filter(user__username=value).exists():
            raise serializers.ValidationError("Student doesn't exist")

        return value


class ReservedNameSerializer(serializers.Serializer):
    """Allows the usage of reserved fieldnames by appending a '_' to the field name in a subclass"""

    def __init__(self, *args, **kwargs):
        super(ReservedNameSerializer, self).__init__(*args, **kwargs)

        fields = self.fields

        for field_name in fields:
            if field_name.endswith("_"):
                fields[field_name[:-1]] = fields.pop(field_name)


class ReservedNameHyperlinkedModelSerializer(serializers.HyperlinkedModelSerializer):
    """Allows the usage of reserved fieldnames by appending a '_' to the field name in a subclass"""

    def __init__(self, *args, **kwargs):
        super(ReservedNameHyperlinkedModelSerializer, self).__init__(*args, **kwargs)

        fields = self.fields

        for field_name in fields:
            if field_name.endswith("_"):
                fields[field_name[:-1]] = fields.pop(field_name)


class MeetingInstanceSerializer(serializers.HyperlinkedModelSerializer):
    lecturer = serializers.CharField()

    class Meta:
        model = MeetingInstance
        fields = ('room', 'date', 'meeting', 'lecturer')


class MeetingSerializer(ReservedNameHyperlinkedModelSerializer):
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
    classes = serializers.HyperlinkedRelatedField(view_name='class-detail', many=True, read_only=True)

    class Meta:
        model = Student
        fields = ('username', 'classes')


class FriendSerializer(serializers.ModelSerializer):
    shared_with = serializers.StringRelatedField(many=True)
    shared_from = serializers.StringRelatedField(many=True)

    class Meta:
        model = Student
        fields = ('shared_with', 'shared_from')


class AllowedTimetableSerializer(serializers.ModelSerializer):
    me = serializers.HyperlinkedRelatedField(view_name='timetable-detail', read_only=True,
                                             lookup_field='username', source='user')
    shared_with_me = serializers.HyperlinkedRelatedField(view_name='timetable-detail', many=True, read_only=True,
                                                         source='shared_from', lookup_field='username')

    def __init__(self, *args, **kwargs):
        base_view = kwargs.pop('base_view')

        super(AllowedTimetableSerializer, self).__init__(*args, **kwargs)

        if base_view is None:
            raise ValueError("No base_view provided")

        self.fields['me'].view_name = base_view + '-detail'
        self.fields['shared_with_me'].child_relation.view_name = base_view + '-detail'

    class Meta:
        model = Student
        fields = ('me', 'shared_with_me')


class TimetableSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    time_start = serializers.TimeField(source='meeting.time_start', read_only=True)
    time_end = serializers.TimeField(source='meeting.time_end', read_only=True)
    date = serializers.DateField(read_only=True)
    class_name = serializers.CharField(source='meeting.class_rel.class_code', read_only=True)
    attended = serializers.BooleanField(source='_attended', read_only=True)
    room_has_beacon = serializers.BooleanField(source='room.has_beacon', read_only=True)
    room_name = serializers.CharField(source='room.room_code', read_only=True)
    building_name = serializers.CharField(source='room.building', read_only=True)
    lecturer = serializers.CharField(read_only=True)
    self = serializers.HyperlinkedIdentityField(view_name='meetinginstance-detail', read_only=True)

    def __init__(self, *args, **kwargs):
        # Instantiate the superclass normally
        super(TimetableSerializer, self).__init__(*args, **kwargs)

        for meeting_instance in self.instance:
            meeting_instance._attended = self.did_attend(meeting_instance)

    def did_attend(self, obj):
        student = self.context['student']
        return AttendanceRecord.objects.filter(student=student, meeting_instance=obj).exists()


class AttendanceRecordSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = ('meeting_instance',)


class StreakField(serializers.Field):
    def __init__(self, many=False, *args, **kwargs):
        self.many = many

        super(StreakField, self).__init__(*args, **kwargs)

    def to_representation(self, value, many=None):
        if many is None:
            many = self.many

        if many:
            reprs = []
            for v in value:
                reprs.append(self.to_representation(v, False))
            return reprs

        return str(value)

    def to_internal_value(self, data) -> Streak:
        if self.many:
            raise NotImplementedError("Not implemented")

        start_str, end_str = data.split('/', 1)

        start = dateutil.parser.parse(start_str).date()
        end = dateutil.parser.parse(end_str).date()

        return Streak(start, end)


class ClassStreaksSerializer(serializers.Serializer):
    url = serializers.HyperlinkedIdentityField(view_name='class-detail', read_only=True)
    class_name = serializers.StringRelatedField(source='class_code')
    streaks = StreakField(read_only=True, source='_streaks', many=True)

    def to_representation(self, instance):
        # A bit of a hack since otherwise we don't have the required instance access
        instance._streaks = instance.attendance_streaks(self.context['student'])
        serialized = super(ClassStreaksSerializer, self).to_representation(instance)
        return serialized


class StreaksSerializer(serializers.ModelSerializer):
    overall = StreakField(read_only=True, many=True, source='overall_streaks')

    def __init__(self, *args, **kwargs):
        super(StreaksSerializer, self).__init__(*args, **kwargs)

        # Need to do this here so that we have access to the context
        self.fields['class_streaks'] = ClassStreaksSerializer(many=True, context=self.context, source='classes')

    class Meta:
        model = Student
        fields = ('overall', 'class_streaks')
