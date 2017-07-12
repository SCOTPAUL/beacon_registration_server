import dateutil.parser
from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .utils import Streak
from .models import Room, Beacon, Building, Class, Meeting, Student, MeetingInstance, AttendanceRecord, LogEntry,\
    Friendship


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


class BeaconSightingDeserializer(serializers.Serializer):
    uuid = serializers.UUIDField(required=True)
    major = serializers.IntegerField(required=True)
    minor = serializers.IntegerField(required=True)
    seen_at_time = serializers.DateTimeField(required=True)


class NicknameChangeSerializer(serializers.Serializer):
    nickname = serializers.CharField(max_length=20, required=True,
                                     validators=[UniqueValidator(queryset=Student.objects.all())])


class NewAccountDeserializer(serializers.Serializer):
    nickname = serializers.CharField(max_length=20, required=True,
                                     validators=[UniqueValidator(queryset=Student.objects.all())])
    username = serializers.CharField(max_length=140, required=True,
                                     validators=[UniqueValidator(queryset=User.objects.all())])
    password = serializers.CharField(required=True)


class StudentDeserializer(serializers.Serializer):
    username = serializers.CharField(max_length=140, required=True)
    auth_token = serializers.CharField(required=True)


class AuthTokenRequestDeserializer(serializers.Serializer):
    username = serializers.CharField(max_length=140, required=True)
    password = serializers.CharField(required=True)


class FriendDeserializer(serializers.Serializer):
    username = serializers.CharField(max_length=140, required=True)


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


class SimpleStudentSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username')
    location_status = serializers.CharField(source='location_status.value')

    class Meta:
        model = Student
        fields = ('username', 'nickname', 'location_status')


class StudentSerializer(serializers.HyperlinkedModelSerializer):
    username = serializers.CharField(source='user.username')
    classes = serializers.HyperlinkedRelatedField(view_name='class-detail', many=True, read_only=True)

    class Meta:
        model = Student
        fields = ('username', 'nickname', 'classes')


class LocationStatusSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    location_status = serializers.CharField(source='location_status.value', read_only=True)

    class Meta:
        model = Student
        fields = ('username', 'location_status')


class LocationSerializer(serializers.Serializer):
    location_status = serializers.CharField(required=True)
    time_start = serializers.TimeField(required=False)
    time_end = serializers.TimeField(required=False)
    room = serializers.CharField(required=False)
    building = serializers.CharField(required=False)
    class_name = serializers.CharField(required=False)


class FriendRequestSerializer(serializers.Serializer):
    from_user_username = serializers.CharField(source='user.username')
    from_user_nickname = serializers.CharField(source='nickname')


class FriendsSerializer(serializers.Serializer):
    friend_requests = FriendRequestSerializer(many=True)
    friends = SimpleStudentSerializer(many=True)

class FriendshipSerializer(serializers.ModelSerializer):
    from_user = serializers.StringRelatedField(source='initiating_student', read_only=True)
    from_user_nickname = serializers.StringRelatedField(source='initiating_student.nickname', read_only=True)
    to_user = serializers.StringRelatedField(source='receiving_student', read_only=True)
    to_user_nickname = serializers.StringRelatedField(source='receiving_student.nickname', read_only=True)

    class Meta:
        model = Friendship
        fields = ('from_user', 'from_user_nickname', 'to_user', 'to_user_nickname', 'accepted')


class AllowedTimetableSerializer(serializers.ModelSerializer):
    me = serializers.HyperlinkedRelatedField(view_name='timetable-detail', read_only=True,
                                             lookup_field='username', source='user')
    shared_with_me = serializers.HyperlinkedRelatedField(view_name='timetable-detail', many=True, read_only=True,
                                                         source='friends', lookup_field='username')

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
    room_has_beacon = serializers.BooleanField(source='had_beacon', read_only=True)
    room_name = serializers.CharField(source='room.room_code', read_only=True)
    building_name = serializers.CharField(source='room.building', read_only=True)
    lecturer = serializers.CharField(read_only=True)
    self = serializers.HyperlinkedIdentityField(view_name='meetinginstance-detail', read_only=True)

    def __init__(self, *args, **kwargs):
        # Instantiate the superclass normally
        super(TimetableSerializer, self).__init__(*args, **kwargs)

        attended_meetings = AttendanceRecord.objects.filter(student=self.context['student'])
        attended_meeting_ids = attended_meetings.values_list('meeting_instance__id', flat=True)

        for meeting_instance in self.instance:
            meeting_instance._attended = meeting_instance.id in attended_meeting_ids


class AttendanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = ('meeting_instance', 'time_attended')


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


class LogEntryDeserializer(serializers.Serializer):
    event_type = serializers.ChoiceField(choices=LogEntry.EVENT_TYPE_CHOICES, required=True)
    event_text = serializers.CharField(required=True)
    timestamp = serializers.DateTimeField(required=True)

