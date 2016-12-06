import calendar

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class Student(models.Model):
    """
    Representation of a student
    """
    user = models.OneToOneField(User)

    def __str__(self):
        return self.user.username

    @property
    def classes(self):
        """
        :return: A QuerySet containing of all the Class objects that this student has at least one Meeting for
        """
        class_ids = self.meeting_set.values('class_rel').distinct()
        return Class.objects.filter(pk__in=class_ids)


class Beacon(models.Model):
    """
    Represents a Bluetooth iBeacon's identifiers and physical Room location
    """
    uuid = models.UUIDField()
    major = models.IntegerField()
    minor = models.IntegerField()
    room = models.ForeignKey('Room', related_name='beacons')

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

    def has_beacon(self):
        return self.beacons.exists()

    def __str__(self):
        return '{}: {}'.format(self.building, self.room_code)


class Class(models.Model):
    """
    Represents a university course, which has some number of Meetings
    """
    class_code = models.CharField(unique=True, max_length=140)

    class Meta:
        verbose_name_plural = 'Classes'

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

    students = models.ManyToManyField('Student')
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
    meeting = models.ForeignKey('Meeting', related_name='instances')
    room = models.ForeignKey('Room', related_name='meeting_instances')

    def __str__(self):
        return '{} in room {} on {}'.format(self.meeting, self.room, self.date)

    def clean(self):
        if self.date.weekday() != self.meeting.day_of_week:
            raise ValidationError("This instance's date falls on a {}, but its related Meeting is on a {}".format(
                                  calendar.day_name[self.date.weekday()],
                                  self.meeting.weekday()))

    def save(self, *args, **kwargs):
        self.full_clean()
        return super(MeetingInstance, self).save(*args, **kwargs)


class AttendanceRecord(models.Model):
    """
    A relation between a MeetingInstance and a Student, which marks that they attended that particular MeetingInstance
    """
    meeting_instance = models.ForeignKey('MeetingInstance', related_name='attendance_records')
    student = models.ForeignKey('Student', related_name='attendance_records')

    def __str__(self):
        return "{} attended {}".format(self.student,
                                       self.meeting_instance)


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
