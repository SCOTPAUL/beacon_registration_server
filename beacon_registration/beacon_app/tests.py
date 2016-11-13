import datetime
import json

from django.contrib.auth.models import User
from django.test import TestCase
from .meetingbuilder import get_or_create_meetings
from .models import Student, Meeting, Class


class TimetableConstruction(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='2082442q')
        self.student = Student.objects.create(user=self.user)

    def test_construction(self):
        f = open('beacon_app/testdata/events.json', 'r')
        lines = f.read()

        data = json.loads(lines)

        inactive_meetings = get_or_create_meetings(data, self.student)

        self.assertEqual(len(self.student.classes.all()), 8)
        self.assertEqual(len(inactive_meetings), 0)

    def test_meetings_inactive(self):
        old_class = Class.objects.create(class_code="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
        self.student.classes.add(old_class)

        old_meeting = Meeting.objects.create(time_start=datetime.time(9, 00), time_end=datetime.time(10, 00),
                                             day_of_week=0, class_rel=old_class)

        f = open('beacon_app/testdata/events.json', 'r')
        lines = f.read()

        data = json.loads(lines)

        inactive_meetings = get_or_create_meetings(data, self.student)

        self.assertEqual(len(inactive_meetings), 1)
