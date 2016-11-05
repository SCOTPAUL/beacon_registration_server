from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from .views import *


router = DefaultRouter()
router.register(r'rooms', RoomViewSet)
router.register(r'buildings', BuildingViewSet)
router.register(r'beacons', BeaconViewSet)
router.register(r'tokens', TokenViewSet)

urlpatterns = router.urls
