"""Forgotten passwords: a patient gets themselves back in, and nobody else in.

The flow is two public calls — ask by phone, then confirm with the mailed uid
and token. What matters here is what the endpoint refuses to say (whether a
number is known) and what the token refuses to do twice.
"""
import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.tenants.current import clear_current_tenant
from apps.tenants.models import Tenant

PASSWORD = "s3curepass99"
NEW_PASSWORD = "an0therpass77"


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(name="Clinic", slug="clinic")
    yield t
    clear_current_tenant()


@pytest.fixture
def patient_user(tenant):
    user = User.objects.create(
        phone="08031234567", email="ada@example.com", tenant=tenant,
        role=Role.PUBLIC,
    )
    user.set_password(PASSWORD)
    user.save()
    return user


def _client():
    """No tenant header: someone locked out has no organization to send."""
    return APIClient()


def _ask(phone):
    return _client().post(
        "/api/auth/password-reset/", {"phone": phone}, format="json"
    )


def _confirm(**body):
    return _client().post(
        "/api/auth/password-reset/confirm/", body, format="json"
    )


def _link_parts():
    """uid and token out of the one mail that was sent."""
    body = mail.outbox[-1].body
    query = body.split("#/reset?", 1)[1].split()[0]
    parts = dict(pair.split("=", 1) for pair in query.split("&"))
    return parts["uid"], parts["token"]


def test_patient_resets_and_signs_in_with_the_new_password(patient_user):
    assert _ask("+234 803 123 4567").status_code == 200  # any phone shape
    assert len(mail.outbox) == 1
    uid, token = _link_parts()

    done = _confirm(uid=uid, token=token, password=NEW_PASSWORD)
    assert done.status_code == 200, done.content

    signin = _client().post(
        "/api/auth/token/",
        {"phone": "08031234567", "password": NEW_PASSWORD},
        format="json",
    )
    assert signin.status_code == 200, signin.content


def test_unknown_number_answers_the_same_and_mails_nothing(patient_user):
    known = _ask("08031234567")
    unknown = _ask("08099999999")
    assert unknown.status_code == known.status_code == 200
    assert unknown.json()["message"] == known.json()["message"]
    assert len(mail.outbox) == 1  # only the known one produced a mail


def test_a_token_works_once(patient_user):
    _ask("08031234567")
    uid, token = _link_parts()
    assert _confirm(uid=uid, token=token, password=NEW_PASSWORD).status_code == 200
    # The hash covers the old password, so changing it retires the token.
    again = _confirm(uid=uid, token=token, password="third0ne55x")
    assert again.status_code == 400
    assert not User.objects.get(pk=patient_user.pk).check_password("third0ne55x")


def test_a_forged_token_is_refused(patient_user):
    _ask("08031234567")
    uid, _token = _link_parts()
    bad = _confirm(uid=uid, token="abc123-notarealtoken", password=NEW_PASSWORD)
    assert bad.status_code == 400
    assert User.objects.get(pk=patient_user.pk).check_password(PASSWORD)
