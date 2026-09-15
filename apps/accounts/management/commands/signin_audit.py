"""Try every seat's sign-in against the live database and name the ones refused.

    python manage.py signin_audit

Each row gets a throwaway password inside one transaction that is rolled back
at the end, so nothing is left changed; the credential tried is the one the
row carries (licence, pharmacy short code, or phone, exactly as stored). Run
it on the deploy after a rollout that touches sign-in or the user table.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test.utils import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import LICENSED_ROLES, Role, User

PW = "signin-audit-throwaway-pw!"


def credential(user):
    if user.role in LICENSED_ROLES and user.license_number:
        return {"license_number": user.license_number}
    if user.role == Role.PHARMACIST:
        return {"phone": user.phone[-6:]}
    return {"phone": user.phone}


def why(user, status):
    if not user.is_active:
        return "closed by an admin (is_active=False)"
    if not user.has_usable_password():
        return "no password set - an admin must set one"
    return f"sign-in answered {status} - the lookup misses this row"


class Command(BaseCommand):
    help = "List every user who cannot sign in with the credential on their row."

    def handle(self, *args, **options):
        # APIClient asks as "testserver", which the deploy's ALLOWED_HOSTS
        # does not name.
        with override_settings(ALLOWED_HOSTS=["testserver"]), transaction.atomic():
            blocked = self.probe()
            transaction.set_rollback(True)
        total = User.objects.count()
        for user, status in blocked:
            self.stdout.write(
                f"#{user.pk} {user.phone} {user.role}: {why(user, status)}"
            )
        self.stdout.write(f"{total - len(blocked)}/{total} seats sign in.")

    def probe(self):
        blocked = []
        for user in User.objects.select_related("tenant").order_by("pk"):
            # The password column only; the probe never re-saves the row.
            User.objects.filter(pk=user.pk).update(
                password=self._hashed(user)
            )
            headers = {"HTTP_X_TENANT_ID": user.tenant.slug} if user.tenant_id else {}
            r = APIClient().post(
                "/api/auth/token/", {**credential(user), "password": PW},
                format="json", **headers,
            )
            if r.status_code != 200:
                blocked.append((user, r.status_code))
        return blocked

    @staticmethod
    def _hashed(user):
        probe = User(pk=user.pk)
        probe.set_password(PW)
        return probe.password
