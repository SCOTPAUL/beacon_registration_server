from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'rooms', RoomViewSet)
router.register(r'accounts', AccountsViewSet, base_name='account')
router.register(r'buildings', BuildingViewSet)
router.register(r'beacons', BeaconViewSet)
router.register(r'tokens', TokenViewSet)
router.register(r'logs', LogEntryViewSet, base_name='log')
router.register(r'classes', ClassViewSet)
router.register(r'meetings', MeetingViewSet)
router.register(r'meeting-instances', MeetingInstanceViewSet)
router.register(r'students', StudentViewSet)
router.register(r'timetables', TimetableViewSet, base_name='timetable')
router.register(r'attendance-records', AttendanceRecordViewSet, base_name='attendance-record')
router.register(r'friends', FriendViewSet, base_name='friend')
router.register(r'attendances', AttendancePercentageViewSet, base_name='attendance')
router.register(r'streaks', StreakViewSet, base_name='streak')
router.register(r'source-code', SourceViewSet, base_name='source')


urlpatterns = router.urls
