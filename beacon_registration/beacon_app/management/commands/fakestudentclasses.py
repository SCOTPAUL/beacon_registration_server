from datetime import date, timedelta, time, datetime
import random

import pytz
from django.core.management import BaseCommand
from django.db import transaction

from beacon_app.models import Meeting, Class, MeetingInstance, Building, Room, Lecturer, AttendanceRecord, Student, Beacon

from beacon_registration import settings

fake_class_names = ["Advanced Sleeping", "Intro To Fake Data", "Django Apps III (H)",
                    "Advanced Android Algorithmics (M)", "Machine Forgetting (H)", "Computer Visionaries 2",
                    "Ice Skating 3", "Dance Dance Revolution M", "Vogon Poetry Analysis"]

fake_room_names = [str(num) for num in range(1000)]
fake_buildings = ["Starbucks", "Queen Margaret Union Garden", "Subway", "Costa Coffee"]


def weighted_choice(choices):
    total_weight = sum((weight for value, weight in choices))
    rand_val = random.uniform(0, total_weight)

    cumulative = 0
    for value, weight in choices:
        if cumulative + weight >= rand_val:
            return value
        cumulative += weight

    # Went over total
    raise OverflowError()


def generate_fake_lecturer_name():
    titles = ["Mr", "Mrs", "Ms", "Miss", "Dr", "Prof"]
    first = ["James", "Bob", "Gregor", "Anne", "Alison", "Claire"]
    second = ["Swanson", "Thompson", "Andrews", "Jenson", "McPherson", "Taylor", "Robertson"]

    return "{} {} {}".format(random.choice(titles), random.choice(first), random.choice(second))


def is_weekday(date_instance):
    day_of_week = date_instance.weekday()
    return day_of_week < 5


@transaction.atomic()
def drop_and_create_all(start_hour, end_hour, attendance_aim=None):
    Class.objects.filter(fake=True).delete()
    Meeting.objects.filter(fake=True).delete()
    MeetingInstance.objects.filter(fake=True).delete()
    Room.objects.filter(fake=True).delete()
    Building.objects.filter(fake=True).delete()
    Lecturer.objects.filter(fake=True).delete()
    AttendanceRecord.objects.filter(fake=True).delete()
    Beacon.objects.filter(fake=True).delete()

    create_fake_meetings(start_hour, end_hour)
    create_fake_student_relations(attendance_aim)


def create_fake_meetings(start_hour, end_hour):
    start_date = date(2016, 8, 1)
    end_date = date(2017, 9, 1)

    fake_beacon_uuid = "f7826da6-4fa2-4e98-8024-bc5b71e0893f"
    fake_beacon_major = 156
    fake_beacon_minor = 0

    valid_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days)]
    valid_weekdays = [day for day in valid_dates if is_weekday(day)]

    for day in valid_weekdays:
        filled_hours = []

        for hour_of_day in range(start_hour, end_hour):
            if hour_of_day in filled_hours:
                continue

            if random.random() > 0.8:
                duration_hrs = min(weighted_choice(((1, 0.5), (2, 0.4), (3, 0.1))), end_hour - hour_of_day)

                for hour in range(hour_of_day, hour_of_day + duration_hrs):
                    filled_hours.append(hour)

                fake_class, _ = Class.objects.get_or_create(class_code=random.choice(fake_class_names), fake=True)
                fake_meeting, _ = Meeting.objects.get_or_create(day_of_week=day.weekday(),
                                                                time_start=time(hour_of_day, 0),
                                                                time_end=time(hour_of_day + duration_hrs, 0),
                                                                class_rel=fake_class,
                                                                fake=True)

                fake_building, _ = Building.objects.get_or_create(name=random.choice(fake_buildings), fake=True)

                fake_room, _ = Room.objects.get_or_create(building=fake_building,
                                                          room_code=random.choice(fake_room_names),
                                                          fake=True)

                if random.random() < 0.8:
                    fake_beacon, _ = Beacon.objects.get_or_create(uuid=fake_beacon_uuid,
                                                                  major=fake_beacon_major,
                                                                  minor=fake_beacon_minor,
                                                                  room=fake_room,
                                                                  date_added=start_date,
                                                                  fake=True)
                    fake_beacon_minor += 1

                fake_lecturer, _ = Lecturer.objects.get_or_create(name=generate_fake_lecturer_name(), fake=True)

                MeetingInstance.objects.get_or_create(date=day, meeting=fake_meeting,
                                                      room=fake_room,
                                                      lecturer=fake_lecturer,
                                                      fake=True)


def create_fake_student_relations(attendance_aim=None):
    tz = pytz.timezone(settings.TIME_ZONE)
    now = datetime.now()

    for student in Student.objects.filter(fake_account=True).all():
        if attendance_aim is None:
            attendance_aim = random.gauss(0.6, 0.25)

        if attendance_aim < 0.0:
            attendance_aim = 0.0
        elif attendance_aim > 1.0:
            attendance_aim = 1.0

        for meeting in Meeting.objects.filter(fake=True).all():
            meeting.students.add(student)
            meeting.save()

            for inst in meeting.instances.all():
                if random.random() < attendance_aim:
                    attended_at = datetime.combine(inst.date, inst.meeting.time_start)
                    if attended_at <= now:

                        AttendanceRecord.objects.get_or_create(meeting_instance=inst,
                                                               student=student,
                                                               time_attended=attended_at.replace(tzinfo=tz),
                                                               manually_created=True,
                                                               fake=True)

        print("Attendance Aim: {}".format(attendance_aim))



class Command(BaseCommand):
    help = 'Adds fake data for fake users'

    def add_arguments(self, parser):
        parser.add_argument('--attendance', action='store', dest='attendance', default=None,
                            type=float, help='The attendance that test users should have')

        parser.add_argument('--start-time', action='store', dest='start_time', default=9,
                            type=int, help='The time that classes can start at (default 9AM)')

        parser.add_argument('--end-time', action='store', dest='end_time', default=17,
                            type=int, help='The time that classes end at (default 5PM)')

    def handle(self, *args, **options):
        attendance = options['attendance']

        drop_and_create_all(attendance_aim=attendance, start_hour=options['start_time'], end_hour=options['end_time'])
        self.stdout.write(self.style.SUCCESS('Generated data'))

