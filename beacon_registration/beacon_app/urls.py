from django.conf.urls import url
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r'rooms', RoomViewSet)
router.register(r'buildings', BuildingViewSet)
router.register(r'beacons', BeaconViewSet)
router.register(r'tokens', TokenViewSet)
router.register(r'classes', ClassViewSet)
router.register(r'meetings', MeetingViewSet, base_name='meeting')
router.register(r'students', StudentViewSet)
router.register(r'timetables', TimetableViewSet, base_name='timetable')


urlpatterns = router.urls
