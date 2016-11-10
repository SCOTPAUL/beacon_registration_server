import json

from django.contrib.auth.models import User
from django.test import TestCase

from .meetingbuilder import json_to_courses, get_or_create_meetings
from .models import Student, Meeting, MeetingInstance


class TimetableConstruction(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='2082442q')
        self.student = Student.objects.create(user=self.user)

    def test_construction(self):
        print(User.objects.all())

        f = open('beacon_app/testdata/events.json', 'r')
        lines = f.read()

        data = json.loads(lines)

        courses = json_to_courses(data)
        get_or_create_meetings(courses, self.student)

        print(Meeting.objects.all())
        print(MeetingInstance.objects.all())
