from django.contrib import admin

from .models import *

admin.site.register(Beacon)
admin.site.register(Room)
admin.site.register(Student)
admin.site.register(AttendanceRecord)


class MeetingInstanceInline(admin.TabularInline):
    model = MeetingInstance
    extra = 0


class MeetingInline(admin.TabularInline):
    model = Meeting
    extra = 0
    max_num = 0
    show_change_link = True
    readonly_fields = ('time_start', 'time_end', 'day_of_week', 'active')
    can_delete = False


class RoomInline(admin.TabularInline):
    model = Room
    extra = 0
    show_change_link = True
    readonly_fields = ('room_code',)


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    inlines = [MeetingInline]


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    inlines = [MeetingInstanceInline]


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    inlines = [RoomInline]
