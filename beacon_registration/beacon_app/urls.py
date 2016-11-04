from rest_framework.routers import DefaultRouter

from .views import *


router = DefaultRouter()
router.register(r'rooms', RoomViewSet)
router.register(r'buildings', BuildingViewSet)
router.register(r'beacons', BeaconViewSet)

urlpatterns = router.urls
