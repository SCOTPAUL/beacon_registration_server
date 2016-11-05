from django.contrib.auth.models import User
from django.db import models


class Demonstrator(models.Model):
    user = models.OneToOneField(User)
    classes = models.ManyToManyField('Class', blank=True)

    def __str__(self):
        return self.user.username


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

    def __str__(self):
        return '{}: {}'.format(self.building, self.room_code)


class Class(models.Model):
    class_code = models.CharField(unique=True, max_length=140)
    demonstrators = models.ManyToManyField('Demonstrator', blank=True)
    students = models.ManyToManyField('Student', blank=True)

    class Meta:
        verbose_name_plural = 'Classes'

    def __str__(self):
        return self.class_code


class Meeting(models.Model):
    _WEEKDAY_STRINGS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']

    WEEKDAY_CHOICES = (
        enumerate(_WEEKDAY_STRINGS)
    )

    time_start = models.TimeField()
    time_end = models.TimeField()
    day_of_week = models.IntegerField(choices=WEEKDAY_CHOICES)

    date_start = models.DateField()
    date_end = models.DateField()

    room = models.ForeignKey('Room', related_name='meetings')
    class_rel = models.ForeignKey('Class', related_name='meetings', verbose_name='Class')

    def weekday(self):
        return self._WEEKDAY_STRINGS[int(self.day_of_week)]

    def __str__(self):
        return '{} at {}-{}, from {} to {}, Room {} for Class {}'.format(
            self.weekday(),
            self.time_start,
            self.time_end,
            self.date_start,
            self.date_end,
            self.room,
            self.class_rel.class_code
        )


class AttendanceRecord(models.Model):
    date = models.DateField()
    meeting = models.ForeignKey('Meeting', related_name='attendance_records')
    student = models.ForeignKey('Student', related_name='attendance_records')


class ShuffledID(models.Model):
    uuid = models.UUIDField()
    major = models.IntegerField()
    minor = models.IntegerField()
    valid_until = models.DateTimeField()
    beacon = models.ForeignKey('Beacon', related_name='shuffled_ids')

    class Meta:
        unique_together = ('uuid', 'major', 'minor')
        verbose_name = 'Shuffled ID'
