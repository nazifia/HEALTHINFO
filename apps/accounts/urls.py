from rest_framework.routers import SimpleRouter

from .views import LogoutViewSet, OnboardingViewSet, RegisterViewSet, UserViewSet

router = SimpleRouter()
router.register("auth/onboarding", OnboardingViewSet, basename="onboarding")
router.register("auth/register", RegisterViewSet, basename="register")
router.register("auth/logout", LogoutViewSet, basename="logout")
router.register("users", UserViewSet, basename="user")

urlpatterns = router.urls
