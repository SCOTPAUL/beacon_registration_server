from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
import calendar


class Student(models.Model):
    user = models.OneToOneField(User)
    classes = models.ManyToManyField('Class', blank=True)

    def __str__(self):
        return self.user.username


class Beacon(models.Model):
    uuid = models.UUIDField()
    major = models.IntegerField()
    minor = models.IntegerField()
    room = models.ForeignKey('Room', related_name='beacons')

    class Meta:
        unique_together = ('uuid', 'major', 'minor')

    def __str__(self):
        return "{}, {}, {}, {}".format(self.uuid, self.major, self.minor, self.room)


class Building(models.Model):
    building_name = models.CharField(unique=True, blank=False, null=False, max_length=140)

    def __str__(self):
        return self.building_name


class Room(models.Model):
    building = models.ForeignKey('Building', null=False, blank=False, related_name='rooms')
    room_code = models.CharField(unique=True, max_length=140)

    class Meta:
        unique_together = ('building', 'room_code')

    def has_beacon(self):
        return self.beacons.exists()

    def __str__(self):
        return '{}: {}'.format(self.building, self.room_code)


class Class(models.Model):
    class_code = models.CharField(unique=True, max_length=140)

    class Meta:
        verbose_name_plural = 'Classes'

    def __str__(self):
        return self.class_code


class MeetingInstance(models.Model):
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


class Meeting(models.Model):
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


class AttendanceRecord(models.Model):
    meeting_instance = models.ForeignKey('MeetingInstance', related_name='attendance_records')
    student = models.ForeignKey('Student', related_name='attendance_records')

    def __str__(self):
        return "{} attended {}".format(self.student,
                                       self.meeting_instance)


class ShuffledID(models.Model):
    uuid = models.UUIDField()
    major = models.IntegerField()
    minor = models.IntegerField()
    valid_until = models.DateTimeField()
    beacon = models.ForeignKey('Beacon', related_name='shuffled_ids')

    class Meta:
        unique_together = ('uuid', 'major', 'minor')
        verbose_name = 'Shuffled ID'
