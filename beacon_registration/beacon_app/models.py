import calendar
import datetime
from enum import Enum
from typing import Dict, List, Union

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.db.models import Q
from django.db.models import QuerySet
from django.utils import timezone

from beacon_app.utils import Streak


class LocationStatus(Enum):
    """
    Indicates current student location status
    """

    """
    The student does not currently have a class scheduled
    """
    NO_CLASS = "no_class"

    """
    The student has a class scheduled for now, and has been marked as attended for that class
    """
    IN_CLASS = "in_class"

    """
    The student has a class scheduled for now, but hasn't yet been marked attended. The Room may have no beacons in it.
    """
    NOT_SEEN_IN_CLASS = "not_seen_in_class"


class Location:
    def __init__(self, meeting_instance: 'MeetingInstance', location_status: LocationStatus):
        self.meeting_instance = meeting_instance
        self.location_status = location_status


class Student(models.Model):
    """
    Representation of a student
    """
    user = models.OneToOneField(User, unique=True)
    date_registered = models.DateField(editable=False, null=False, blank=False, auto_now_add=True)
    nickname = models.CharField(null=False, blank=False, unique=True, max_length=20)

    def __str__(self):
        return self.user.username

    @property
    def friends(self) -> QuerySet:
        """
        :return: QuerySet of friends for this student
        """
        return Student.objects.filter(Q(initiated_friendships__accepted=True,
                                        initiated_friendships__receiving_student=self) |
                                      Q(received_friendships__accepted=True,
                                        received_friendships__initiating_student=self)).exclude(pk=self.pk).distinct()

    @property
    def location(self) -> Dict:
        location_dict = {'meeting_instance': None, 'location_status': None}

        current_datetime = datetime.datetime.now()
        classes_on_now = MeetingInstance.objects.filter(
            meeting=self.meeting_set.filter(
                time_start__lte=current_datetime.time(),
                time_end__gte=current_datetime.time()),
            date=current_datetime.date()
        )

        if not classes_on_now.exists():
            location_dict['location_status'] = LocationStatus.NO_CLASS.value
            return location_dict
        else:
            student_attendances = AttendanceRecord.objects.filter(student=self)

            for meeting_instance in classes_on_now:
                if student_attendances.filter(meeting_instance=meeting_instance).exists():
                    location_dict['meeting_instance'] = meeting_instance
                    location_dict['location_status'] = LocationStatus.IN_CLASS.value
                    return location_dict

            location_dict['meeting_instance'] = classes_on_now[-1]
            location_dict['location_status'] = LocationStatus.NO_CLASS.value
            return location_dict

    @property
    def location_status(self) -> LocationStatus:
        """
        :return: a location status for the student at the current time
        """
        current_datetime = datetime.datetime.now()
        classes_on_now = MeetingInstance.objects.filter(
            meeting=self.meeting_set.filter(
                time_start__lte=current_datetime.time(),
                time_end__gte=current_datetime.time()),
            date=current_datetime.date()
        )

        if not classes_on_now.exists():
            return LocationStatus.NO_CLASS
        else:
            student_attendances = AttendanceRecord.objects.filter(student=self)

            for meeting_instance in classes_on_now:
                if student_attendances.filter(meeting_instance=meeting_instance).exists():
                    return LocationStatus.IN_CLASS

            return LocationStatus.NOT_SEEN_IN_CLASS

    @property
    def friendships(self) -> QuerySet:
        """
        :return: A QuerySet containing all of the accepted Friendships containing this user
        """
        return Friendship.objects.filter(Q(accepted=True) & (Q(receiving_student=self) | Q(initiating_student=self)))

    @property
    def friend_requests_for_me(self) -> QuerySet:
        """
        :return: A QuerySet containing all of the non-accepted Friendships with this user as the recipient
        """
        return Friendship.objects.filter(accepted=False, receiving_student=self)

    @property
    def classes(self) -> QuerySet:
        """
        :return: A QuerySet containing of all the Class objects that this student has at least one Meeting for
        """
        class_ids = self.meeting_set.values('class_rel').distinct()
        return Class.objects.filter(pk__in=class_ids)

    @property
    def attendances(self) -> Dict['Class', float]:
        """
        :return: a dictionary mapping from Class objects to float attendance percentages
        """
        attendances = {}
        for class_ in self.classes:
            attendances[class_] = class_.attendance(self)

        return attendances

    def class_streaks(self, class_: 'Class') -> List[Streak]:
        """
        :param class_: the Class to get Streaks for
        :return: a list of all of the attendance Streaks that the Student has for that Class
        """
        return class_.attendance_streaks(self)

    @property
    def streaks(self) -> Dict['Class', List[Streak]]:
        """
        :return: a dictionary mapping from Class objects to lists of attendance Streaks
        """
        streaks = {}

        for class_ in self.classes:
            streaks[class_] = class_.attendance_streaks(self)

        return streaks

    @property
    def overall_streaks(self) -> List[Streak]:
        return attendance_streaks(self)

    @property
    def username(self) -> str:
        return self.user.username


class Lecturer(models.Model):
    """
    Representation of a person who leads a class meeting
    """

    name = models.CharField(unique=True, blank=False, null=False, max_length=140)

    def __str__(self):
        return self.name


class Friendship(models.Model):
    """
    Representation of a friendship between two Students
    """

    initiating_student = models.ForeignKey(Student, null=False, blank=False, related_name='initiated_friendships')
    receiving_student = models.ForeignKey(Student, null=False, blank=False, related_name='received_friendships')
    accepted = models.BooleanField(default=False, null=False, blank=False)

    def __str__(self):
        return "Friendship from {} to {}, accepted={}".format(self.initiating_student,
                                                              self.receiving_student,
                                                              self.accepted)

    def clean(self):
        if self.initiating_student == self.receiving_student:
            raise ValidationError("Cannot add self as a friend")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super(Friendship, self).save(*args, **kwargs)


class Beacon(models.Model):
    """
    Represents a Bluetooth iBeacon's identifiers and physical Room location
    """
    uuid = models.UUIDField()
    major = models.IntegerField()
    minor = models.IntegerField()
    room = models.ForeignKey('Room', related_name='beacons')
    date_added = models.DateField(default=timezone.now)

    class Meta:
        unique_together = ('uuid', 'major', 'minor')

    def __str__(self):
        return "{}, {}, {}, {}".format(self.uuid, self.major, self.minor, self.room)


class Building(models.Model):
    """
    A collection of Rooms, in the same building
    """
    name = models.CharField(unique=True, blank=False, null=False, max_length=140)

    def __str__(self):
        return self.name


class Room(models.Model):
    """
    Represents a room in a building
    """
    building = models.ForeignKey('Building', null=False, blank=False, related_name='rooms')
    room_code = models.CharField(unique=True, max_length=140)

    class Meta:
        unique_together = ('building', 'room_code')

    def __str__(self):
        return '{}: {}'.format(self.building, self.room_code)

    def had_beacon(self, date: datetime.date) -> bool:
        """
        :return: if there was at least one beacon in the Room on the date
        """
        return self.beacons.filter(date_added__lte=date).exists()


class Class(models.Model):
    """
    Represents a university course, which has some number of Meetings
    """
    class_code = models.CharField(unique=True, max_length=140)

    class Meta:
        verbose_name_plural = 'Classes'

    def attendance(self, student: Student) -> float:
        today = datetime.date.today()
        time_now = datetime.datetime.now().time()
        meetings = student.meeting_set.filter(class_rel=self)
        instances = MeetingInstance.objects.filter(meeting__in=meetings)
        contributing = instances.filter(Q(date__gte=student.date_registered) &
                                        ((Q(date__lt=today) | Q(date=today, meeting__time_start__gte=time_now)) &
                                         Q(room__beacons__isnull=False) &
                                         Q(room__beacons__date_added__lte=F('date')))
                                        )

        count = 0
        for instance in contributing:
            if instance.attended_by(student):
                count += 1

        if contributing.count() != 0:
            return (count / contributing.count()) * 100.0
        else:
            return 100.0

    def attendance_streaks(self, student: Student) -> List[Streak]:
        return attendance_streaks(student, class_=self)

    def __str__(self):
        return self.class_code


class Meeting(models.Model):
    """
    Represents some sort of class gathering, e.g. a lecture, lab, tutorial etc.
    A subset of the students enrolled in the class are related to this meeting,
    meaning that this is one of the Meetings that they should attend.
    """
    WEEKDAY_CHOICES = (
        enumerate(list(calendar.day_name))
    )

    students = models.ManyToManyField('Student', db_index=True)
    time_start = models.TimeField()
    time_end = models.TimeField()
    day_of_week = models.IntegerField(choices=WEEKDAY_CHOICES, null=False, blank=False)

    class_rel = models.ForeignKey('Class', related_name='meetings', verbose_name='Class')

    def weekday(self) -> str:
        if self.day_of_week is not None:
            return calendar.day_name[self.day_of_week]
        else:
            return ""

    def __str__(self) -> str:
        return '{} at {}-{} for {}'.format(
            self.weekday(),
            self.time_start,
            self.time_end,
            self.class_rel.class_code
        )


class MeetingInstance(models.Model):
    """
    A particular occurrence of a Meeting on a date, along with the Room that the instance occurs in.

    For example, if a class has one lecture in a different room every week, that class will only have one related
    Meeting, but that meeting will have many MeetingInstances, each of which have a different Room.
    """
    date = models.DateField()
    meeting = models.ForeignKey('Meeting', related_name='instances', db_index=True)
    room = models.ForeignKey('Room', related_name='meeting_instances')
    lecturer = models.ForeignKey('Lecturer', related_name='meeting_instances', null=True, blank=True)

    class Meta:
        unique_together = ('date', 'meeting', 'room')

    def __str__(self):
        return '{} in room {} on {}'.format(self.meeting, self.room, self.date)

    def clean(self):
        if self.date.weekday() != self.meeting.day_of_week:
            raise ValidationError("This instance's date falls on a {}, but its related Meeting is on a {}".format(
                calendar.day_name[self.date.weekday()],
                self.meeting.weekday()))

    def attended_by(self, student: Student):
        return AttendanceRecord.objects.filter(meeting_instance=self, student=student).exists()

    @property
    def had_beacon(self) -> bool:
        """
        :return: if there was at least one beacon in the room when the MeetingInstance took place
        """
        return self.room.had_beacon(self.date)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super(MeetingInstance, self).save(*args, **kwargs)


class AttendanceRecord(models.Model):
    """
    A relation between a MeetingInstance and a Student, which marks that they attended that particular MeetingInstance
    """
    meeting_instance = models.ForeignKey('MeetingInstance', related_name='attendance_records', db_index=True)
    student = models.ForeignKey('Student', related_name='attendance_records', db_index=True)
    time_attended = models.TimeField(editable=False, null=False, blank=False, auto_now_add=True)

    class Meta:
        unique_together = ('meeting_instance', 'student')

    def __str__(self):
        return "{} attended {} at {}".format(self.student,
                                             self.meeting_instance,
                                             self.time_attended)

    def clean(self):
        if self.student not in self.meeting_instance.meeting.students.all():
            raise ValidationError("Can't create attendance record, student {} is not enrolled in meeting {}".format(
                self.student,
                self.meeting_instance.meeting))

    def attended_by(self, student: Student) -> bool:
        return AttendanceRecord.objects.filter(meeting_instance=self, student=student).exists()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super(AttendanceRecord, self).save(*args, **kwargs)


class ShuffledID(models.Model):
    """
    Represents the 'faked out' public identifiers broadcast by a Kontakt iBeacon using Kontakt Secure Shuffling,
    along with the real Beacon that these shuffled identifiers represent at a period of time ending at valid_until.
    """
    uuid = models.UUIDField()
    major = models.IntegerField()
    minor = models.IntegerField()
    valid_until = models.DateTimeField()
    beacon = models.ForeignKey('Beacon', related_name='shuffled_ids')

    class Meta:
        unique_together = ('uuid', 'major', 'minor')
        verbose_name = 'Shuffled ID'


def attendance_streaks(student: Student, class_: Union[None, Class] = None) -> List[Streak]:
    today = datetime.date.today()
    time_now = datetime.datetime.now().time()

    if class_ is not None:
        meetings = student.meeting_set.filter(class_rel=class_)
    else:
        meetings = student.meeting_set.all()

    instances = MeetingInstance.objects.filter(meeting__in=meetings)
    contributing = instances.filter(Q(date__gte=student.date_registered) &
                                    ((Q(date__lt=today) | Q(date=today, meeting__time_end__lte=time_now)) &
                                     Q(room__beacons__isnull=False) &
                                     Q(room__beacons__date_added__lte=F('date'))))
    sorted_ = contributing.order_by('date')

    streaks = []

    streak_start = None
    for instance in sorted_:
        attended = instance.attended_by(student)

        if attended and streak_start is None:
            # Start of a streak
            streak_start = instance
        elif not attended and streak_start is not None:
            # End of a streak
            streaks.append(Streak(streak_start.date, instance.date))
            streak_start = None

    if streak_start is not None:
        # A streak started, but has not yet ended
        valid_instances = instances.filter(room__beacons__isnull=False).order_by('-date')
        if len(valid_instances) > 0:
            last_date_of_year = valid_instances[0].date
        else:
            last_date_of_year = today

        if last_date_of_year > today:
            # There is another meeting after today, so the streak can go to today
            streaks.append(Streak(streak_start.date, today))
        else:
            # There are no more meetings after today, so just set the streak as reaching to the last meeting
            streaks.append(Streak(streak_start.date, last_date_of_year))

    return streaks


class LogEntry(models.Model):
    UNKNOWN = 'unknown'
    VIEW = 'view'
    API = 'api'
    ERROR = 'error'
    BEACON = 'beacon'
    COMMS = 'comms'
    LOOKUP = 'lookup'
    APP = 'app'
    DEVICE = 'device'
    TRACKING = 'tracking'
    SERVER = 'server'

    EVENT_TYPE_CHOICES = (
        (UNKNOWN, UNKNOWN),
        (VIEW, VIEW),
        (API, API),
        (ERROR, ERROR),
        (BEACON, BEACON),
        (COMMS, COMMS),
        (LOOKUP, LOOKUP),
        (APP, APP),
        (DEVICE, DEVICE),
        (TRACKING, TRACKING),
        (SERVER, SERVER)
    )

    event_type = models.CharField(max_length=10, choices=EVENT_TYPE_CHOICES, default=UNKNOWN, blank=False, null=False,
                                  editable=False)
    event_text = models.TextField(blank=False, null=False, editable=False)
    timestamp = models.DateTimeField(blank=False, null=False, editable=False)
    server_timestamp = models.DateTimeField(blank=False, null=False, auto_now_add=True, editable=False)
    student = models.ForeignKey(Student, null=True, blank=True, related_name='log_entries')

    def __str__(self):
        return "Student: {}, event_type: {}, timestamp: {}".format(self.student, self.event_type, self.timestamp)

    class Meta:
        verbose_name_plural = 'Log Entries'
