import datetime
import json

from django.contrib.auth.models import User
from django.test import TestCase
from freezegun import freeze_time
from rest_framework.authtoken.models import Token
import dateutil.parser
from rest_framework.test import APIRequestFactory, force_authenticate, RequestsClient
from .meetingbuilder import get_or_create_meetings
from .models import Student, Meeting, Class, Building, Room, MeetingInstance, Beacon, Friendship, AttendanceRecord
from .views import TimetableViewSet, AttendanceRecordViewSet
from .crypto import PasswordCrypto


class Timetables(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='2072452q')
        self.user2 = User.objects.create_user(username='2072452n')
        self.user3 = User.objects.create_user(username='2072452y')
        self.student = Student.objects.create(user=self.user, nickname="s1")
        self.student2 = Student.objects.create(user=self.user2, nickname="s2")
        self.student3 = Student.objects.create(user=self.user3, nickname="s3")
        self.token = Token.objects.create(user=self.user)

    def test_construction(self):
        f = open('beacon_app/testdata/events.json', 'r')
        lines = f.read()

        data = json.loads(lines)

        inactive_meetings = get_or_create_meetings(data, self.student)

        self.assertEqual(len(self.student.classes), 8)
        self.assertEqual(len(inactive_meetings), 0)

        self.assertEqual(MeetingInstance.objects.filter(room=None).count(), 1)

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

        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})

        response = client.get('http://testserver/api/timetables/2072452q/?day=2016-09-26')

        self.assertEqual(len(response.json()), 0)

    def test_timetable_correct(self):
        f = open('beacon_app/testdata/events.json', 'r')
        lines = f.read()

        data = json.loads(lines)

        inactive_meetings = get_or_create_meetings(data, self.student)

        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})

        response = client.get('http://testserver/api/timetables/2072452q/?day=2016-09-26')

        self.assertTrue(
            any(entry['time_start'] == '12:00:00' and entry['class_name'] == 'CVMA (H)' for entry in response.json()))

    def test_access_shared_timetables(self):

        Friendship.objects.create(initiating_student=self.student, receiving_student=self.student3, accepted=True)


        # Self
        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})
        response = client.get('http://testserver/api/timetables/2072452q/')
        self.assertEqual(response.status_code, 200)

        # Shared
        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})
        response = client.get('http://testserver/api/timetables/2072452y/')
        self.assertEqual(response.status_code, 200)

        # Not shared
        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})
        response = client.get('http://testserver/api/timetables/2072452n/')
        self.assertEqual(response.status_code, 403)

        # Non existent
        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})
        response = client.get('http://testserver/api/timetables/2072452z/')
        self.assertEqual(response.status_code, 404)


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
        self.token = Token.objects.create(user=self.user)
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
        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})
        response = client.get('http://testserver/api/timetables/2072452q/?day=2016-12-5')

        self.assertFalse(response.json()[0]['attended'])

        # Add attendance record
        view = AttendanceRecordViewSet.as_view({'post': 'create'})
        beacon_data = {'uuid': '123e4567-e89b-12d3-a456-426655440000', 'major': 1, 'minor': 1,
                       'seen_at_time': dateutil.parser.parse("Dec 5th, 2016 09:00:00")}
        request = factory.post('/attendance-records/', beacon_data)
        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 201)  # 201 Created

        # Check marked as attended
        client = RequestsClient()
        client.headers.update({'Authorization': 'Token ' + str(self.token.key)})
        response = client.get('http://testserver/api/timetables/2072452q/?day=2016-12-5')

        self.assertTrue(response.json()[0]['attended'])

    @freeze_time("Dec 5th, 2016 11:00:00")
    def test_wrong_time(self):
        factory = APIRequestFactory()
        view = AttendanceRecordViewSet.as_view({'post': 'create'})
        beacon_data = {'uuid': '123e4567-e89b-12d3-a456-426655440000', 'major': 1, 'minor': 1,
                       'seen_at_time': dateutil.parser.parse("Dec 5th, 2016 11:00:00")}

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
        beacon_data = {'uuid': '123e4567-e89b-12d3-a456-426655440000', 'major': 1, 'minor': 2,
                       'seen_at_time': dateutil.parser.parse("Dec 5th, 2016 09:00:00")}

        request = factory.post('/attendance-records/', beacon_data)

        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'No such beacon exists')

        # Test for existing beacon details, where the student doesn't have a meeting in that room
        existing_beacon_data = {'uuid': '123e4567-e89b-12d3-a456-426655440000', 'major': 2, 'minor': 1,
                                'seen_at_time': dateutil.parser.parse("Dec 5th, 2016 09:00:00")
        }

        request = factory.post('/attendance-records/', existing_beacon_data)

        force_authenticate(request, user=self.user)
        response = view(request)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'The student is not in a class where this beacon is')


class Crypto(TestCase):

    def test_crypto(self):
        password = "MyNameIsJim123$$"
        self.user = User.objects.create_user(username='2072452q', password=password)

        cipher = PasswordCrypto(self.user)

        ciphertext = cipher.encrypt(password)
        plaintext = cipher.decrypt(ciphertext)

        self.assertEqual(password, plaintext)
        self.assertNotEqual(password, ciphertext)
