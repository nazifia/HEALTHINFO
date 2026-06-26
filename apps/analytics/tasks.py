from celery import shared_task


# ignore_result: fire-and-forget. Storing a result makes .delay() touch the
# result backend on publish, which hangs the request for ~2min when Redis is down.
@shared_task(ignore_result=True)
def record_event(
    tenant_id, user_id, event_type, query="", object_type="", object_id=None,
    result_count=None,
):
    from .models import AnalyticsEvent

    AnalyticsEvent.all_objects.create(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=event_type,
        query=query,
        object_type=object_type,
        object_id=object_id,
        result_count=result_count,
    )


@shared_task
def weekly_tenant_report():
    """Build a per-tenant weekly rollup + outbreak alerts and email tenant admins.

    Runs under beat (Mondays 04:00). Binds each tenant in turn so the
    tenant-scoped stats functions resolve correctly, then restores the prior
    context. Email is best-effort (fail_silently) — no SMTP in dev just logs.
    """
    import logging

    from django.core.mail import send_mail

    from apps.accounts.models import Role, User
    from apps.tenants.current import get_current_tenant, set_current_tenant
    from apps.tenants.models import Tenant

    from .stats import case_report_stats, tenant_stats
    from .surveillance import tenant_spikes

    log = logging.getLogger("analytics.report")
    previous = get_current_tenant()
    sent = 0
    try:
        for tenant in Tenant.objects.all():
            set_current_tenant(tenant)
            report = {
                "tenant": tenant.name,
                "activity": tenant_stats(),
                "cases": case_report_stats(),
                "outbreak_alerts": tenant_spikes(),
            }
            log.info("weekly report for %s: %s", tenant.slug, report)
            recipients = list(
                User.objects.filter(tenant=tenant, role=Role.TENANT_ADMIN)
                .exclude(email="")
                .values_list("email", flat=True)
            )
            if recipients:
                alerts = report["outbreak_alerts"]
                subject = f"[{tenant.name}] Weekly health report"
                if alerts:
                    subject += f" — {len(alerts)} outbreak alert(s)"
                send_mail(
                    subject,
                    f"Weekly summary:\n{report}",
                    None,  # DEFAULT_FROM_EMAIL
                    recipients,
                    fail_silently=True,
                )
                sent += 1
    finally:
        set_current_tenant(previous)
    return {"tenants": Tenant.objects.count(), "emails": sent}
