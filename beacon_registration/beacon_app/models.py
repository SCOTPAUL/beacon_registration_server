import calendar
import datetime

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models import QuerySet
from typing import Dict, Tuple, List

from beacon_app.utils import Streak


class Student(models.Model):
    """
    Representation of a student
    """
    user = models.OneToOneField(User, unique=True)
    shared_with = models.ManyToManyField('Student', related_name='shared_from', blank=True)

    def __str__(self):
        return self.user.username

    @property
    def classes(self) -> QuerySet:
        """
        :return: A QuerySet containing of all the Class objects that this student has at least one Meeting for
        """
        class_ids = self.meeting_set.values('class_rel').distinct()
        return Class.objects.filter(pk__in=class_ids)

    @property
    def attendances(self) -> Dict['Class', float]:
        attendances = {}
        for class_ in self.classes:
            attendances[class_] = class_.attendance(self)

        return attendances

    def class_streaks(self, class_: 'Class'):
        return class_.attendance_streaks(self)

    @property
    def streaks(self) -> Dict['Class', List[Streak]]:
        streaks = {}

        for class_ in self.classes:
            streaks[class_] = class_.attendance_streaks(self)

        return streaks


    @property
    def username(self):
        return self.user.username


class Lecturer(models.Model):
    """
    Representation of a person who leads a class meeting
    """

    name = models.CharField(unique=True, blank=False, null=False, max_length=140)

    def __str__(self):
        return self.name


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

    @property
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

    def attendance(self, student: Student) -> float:
        today = datetime.date.today()
        time_now = datetime.datetime.now().time()
        meetings = student.meeting_set.filter(class_rel=self)
        instances = MeetingInstance.objects.filter(meeting__in=meetings)
        contributing = instances.filter((Q(date__lt=today) | Q(date=today, meeting__time_start__gte=time_now)) & Q(room__beacons__isnull=False))

        count = 0
        for instance in contributing:
            if instance.attended_by(student):
                count += 1

        if contributing.count() != 0:
            return count / contributing.count()
        else:
            return 100.0

    def attendance_streaks(self, student: Student) -> List[Streak]:
        today = datetime.date.today()
        time_now = datetime.datetime.now().time()
        meetings = student.meeting_set.filter(class_rel=self)

        instances = MeetingInstance.objects.filter(meeting__in=meetings)
        contributing = instances.filter((Q(date__lt=today) | Q(date=today, meeting__time_end__lte=time_now)) & Q(room__beacons__isnull=False))
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
