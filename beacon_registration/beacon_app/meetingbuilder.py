import datetime
import dateutil.parser
from collections import defaultdict
from typing import Dict, List, Any, Tuple

from .models import Class, Student, Meeting, Building, Room, MeetingInstance

Event = Dict[str, Any]
Courses = Dict[str, List[Event]]
MeetingInstancesT = List[Event]
MeetingT = Tuple[int, datetime.time, datetime.time]


def parse_events(events: List[Dict[Any, Any]]) -> List[Event]:
    def identity(val):
        return val

    def split_room(val: str):
        return tuple(val.split(':', 1))

    def make_time(val: str):
        return datetime.datetime.strptime(val, '%Y-%m-%d %X').time()

    def make_date(val: str):
        return dateutil.parser.parse(val).date()

    keys_and_transforms = [('room', split_room), ('course', identity), ('start', make_time), ('end', make_time),
                           ('date', make_date)]

    parsed_events = []
    for event in events:
        new_event = {keep_key[0]: keep_key[1](event[keep_key[0]]) for keep_key in keys_and_transforms}

        parsed_events.append(new_event)

    return parsed_events


def events_to_courses(events: List[Event]) -> Courses:
    events_by_course = defaultdict(list)

    for event in events:
        course = event.pop('course', None)
        events_by_course[course].append(event)

    return events_by_course


def course_to_meetings(events: List[Event]) -> Dict[MeetingT, MeetingInstancesT]:
    events_by_weekday = defaultdict(list)

    for event in events:
        weekday = event['date'].weekday()
        start_time = event.pop('start', None)
        end_time = event.pop('end', None)

        events_by_weekday[(weekday, start_time, end_time)].append(event)

    return events_by_weekday


def json_to_courses(json_data: List[Dict]) -> Dict[str, Dict[MeetingT, MeetingInstancesT]]:
    events = parse_events(json_data)
    courses = events_to_courses(events)

    for course_name in courses:
        courses[course_name] = course_to_meetings(courses[course_name])

    return courses


def get_or_create_meetings(json_data: List[Dict], student: Student):
    courses = json_to_courses(json_data)
    active_meeting_pks = []

    for course_name, meetings in courses.items():
        class_ = Class.objects.get_or_create(class_code=course_name)[0]

        if not class_.student_set.filter(pk=student.pk).exists():
            class_.student_set.add(student)

        for meeting, instances in meetings.items():
            meeting, created = Meeting.objects.get_or_create(time_start=meeting[1], time_end=meeting[2],
                                                             day_of_week=meeting[0],
                                                             class_rel=class_)

            if not created and not meeting.active:
                meeting.active = True
                meeting.save()

            active_meeting_pks.append(meeting.pk)

            for instance in instances:
                building = Building.objects.get_or_create(building_name=instance['room'][0])[0]
                room = Room.objects.get_or_create(building=building, room_code=instance['room'][1])[0]

                MeetingInstance.objects.get_or_create(date=instance['date'], room=room, meeting=meeting)

    student_meetings = Meeting.objects.filter(class_rel__student=student)
    inactive_meetings = student_meetings.exclude(pk__in=active_meeting_pks)
    inactive_meetings.update(active=False)

    return inactive_meetings
