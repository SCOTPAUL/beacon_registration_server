import datetime
import json

from django.contrib.auth.models import User
from django.test import TestCase
from freezegun import freeze_time
from rest_framework.authtoken.models import Token
from rest_framework.test import APIRequestFactory, force_authenticate, RequestsClient
from .meetingbuilder import get_or_create_meetings
from .models import Student, Meeting, Class, Building, Room, MeetingInstance, Beacon
from .views import TimetableViewSet, AttendanceRecordViewSet


class TimetableConstruction(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='2072452q')
        self.student = Student.objects.create(user=self.user)

    def test_construction(self):
        f = open('beacon_app/testdata/events.json', 'r')
        lines = f.read()

        data = json.loads(lines)

        inactive_meetings = get_or_create_meetings(data, self.student)

        self.assertEqual(len(self.student.classes), 8)
        self.assertEqual(len(inactive_meetings), 0)

    def test_meetings_inactive(self):
        old_class = Class.objects.create(class_code="Advanced Sleeping")

        old_meeting = Meeting.objects.create(time_start=datetime.time(9, 00), time_end=datetime.time(10, 00),
                                             day_of_week=0, class_rel=old_class)

        self.student.meeting_set.add(old_meeting)

        f = open('beacon_app/testdata/events.json', 'r')
        lines = f.read()

        data = json.loads(lines)

        inactive_meetings = get_or_create_meetings(data, self.student)

        self.assertEqual(len(inactive_meetings), 1)

    def test_meetings_inactive2(self):
        f = open('beacon_app/testdata/events.json', 'r')
        lines = f.read()

        data = json.loads(lines)

        inactive_meetings = get_or_create_meetings(data, self.student)
        inactive_meetings = get_or_create_meetings([], self.student)

        factory = APIRequestFactory()
        view = TimetableViewSet.as_view({'get': 'list'})

        request = factory.get('/timetables/')

        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(len(response.data), 0)

    def test_timetable_correct(self):
        f = open('beacon_app/testdata/events.json', 'r')
        lines = f.read()

        data = json.loads(lines)

        inactive_meetings = get_or_create_meetings(data, self.student)

        factory = APIRequestFactory()
        view = TimetableViewSet.as_view({'get': 'list'})

        request = factory.get('/timetables/?day=2016-09-26')

        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertTrue(
            any(entry['time_start'] == '12:00:00' and entry['class_name'] == 'CVMA (H)' for entry in response.data))


class Tokens(TestCase):
    @freeze_time("Jan 14th, 2020")
    def setUp(self):
        self.user = User.objects.create_user(username='2072452q')
        self.student = Student.objects.create(user=self.user)
        self.token = Token.objects.create(user=self.user)

    @freeze_time("Jan 14th, 2020")
    def test_token_use(self):
        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})

        response = client.get('http://testserver/api/timetables/')

        self.assertEqual(response.status_code, 200)

    @freeze_time("Jan 14th, 2020")
    def test_invalid_token_rejected(self):
        client = RequestsClient()

        # Uses the Token model's internal key generation method
        random_token = self.token.generate_key()

        client.headers.update({'Authorization': 'Token ' + random_token})

        response = client.get('http://testserver/api/timetables/')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Invalid token')

    @freeze_time("Jan 16th, 2020")
    def test_token_expiration(self):
        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})

        response = client.get('http://testserver/api/timetables/')

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'Token has expired')


class AttendanceRecords(TestCase):
    @freeze_time("Dec 5th, 2016")
    def setUp(self):
        self.user = User.objects.create_user(username='2072452q')
        self.student = Student.objects.create(user=self.user)
        self.building = Building.objects.create(name="My House")
        self.beaconed_room = Room.objects.create(building=self.building, room_code="My Room")
        self.unbeaconed_room = Room.objects.create(building=self.building, room_code="Not My Room")
        self.other_beaconed_room = Room.objects.create(building=self.building, room_code="Also Not My Room")

        self.class_ = Class.objects.create(class_code="Advanced Sleeping")
        self.beacon = Beacon.objects.create(uuid='123e4567-e89b-12d3-a456-426655440000', major=1, minor=1,
                                            room=self.beaconed_room)
        self.beacon2 = Beacon.objects.create(uuid='123e4567-e89b-12d3-a456-426655440000', major=2, minor=1,
                                             room=self.other_beaconed_room)

        self.meeting1 = Meeting.objects.create(time_start=datetime.time(9, 00), time_end=datetime.time(10, 00),
                                               day_of_week=0, class_rel=self.class_)

        self.meeting1inst1 = MeetingInstance.objects.create(date=datetime.date.today(), meeting=self.meeting1,
                                                            room=self.beaconed_room)
        self.meeting1inst2 = MeetingInstance.objects.create(date=datetime.date.today() + datetime.timedelta(days=7),
                                                            meeting=self.meeting1, room=self.unbeaconed_room)

        self.student.meeting_set.add(self.meeting1)

    @freeze_time("Dec 5th, 2016 09:00:00")
    def test_create_attendance_record(self):
        factory = APIRequestFactory()

        # Check not marked as attended
        view = TimetableViewSet.as_view({'get': 'list'})
        request = factory.get('/timetables/?day=2016-12-5')
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertFalse(response.data[0]['attended'])

        # Add attendance record
        view = AttendanceRecordViewSet.as_view({'post': 'create'})
        beacon_data = {'uuid': '123e4567-e89b-12d3-a456-426655440000', 'major': 1, 'minor': 1}
        request = factory.post('/attendance-records/', beacon_data)
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertEqual(response.status_code, 200)

        # Check marked as attended
        view = TimetableViewSet.as_view({'get': 'list'})
        request = factory.get('/timetables/?day=2016-12-5')
        force_authenticate(request, user=self.user)
        response = view(request)
        self.assertTrue(response.data[0]['attended'])

    @freeze_time("Dec 5th, 2016 11:00:00")
    def test_wrong_time(self):
        factory = APIRequestFactory()
        view = AttendanceRecordViewSet.as_view({'post': 'create'})
        beacon_data = {'uuid': '123e4567-e89b-12d3-a456-426655440000', 'major': 1, 'minor': 1}

        request = factory.post('/attendance-records/', beacon_data)

        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'The student is not in a class where this beacon is')

    @freeze_time("Dec 5th, 2016 09:00:00")
    def test_wrong_beacon(self):

        # Test for non existent beacon details
        factory = APIRequestFactory()
        view = AttendanceRecordViewSet.as_view({'post': 'create'})
        beacon_data = {'uuid': '123e4567-e89b-12d3-a456-426655440000', 'major': 1, 'minor': 2}

        request = factory.post('/attendance-records/', beacon_data)

        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'No such beacon exists')

        # Test for existing beacon details, where the student doesn't have a meeting in that room
        existing_beacon_data = {'uuid': '123e4567-e89b-12d3-a456-426655440000', 'major': 2, 'minor': 1}

        request = factory.post('/attendance-records/', existing_beacon_data)

        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'The student is not in a class where this beacon is')
