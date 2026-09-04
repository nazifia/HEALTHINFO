"""Reports: sales, inventory, customers, profit, cashier takings, staff pay.

Two rules run through all of them and are the reason the maths looks fussier
than a sum:

* **A refund is recognised on the day it happens**, never against the day of
  the sale it undoes. Charging a March refund back to a February sale would
  rewrite February after the books were read.
* **A line with no recorded cost is not a free line.** It is left out of cost
  of goods and counted in ``cost_coverage`` instead, because treating its cost
  as zero would report the whole sale as profit.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
)
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsPharmacyStaff,
    IsTenantMember,
    is_pharmacy_admin,
)
from apps.customers.models import Customer, WalletTransaction
from apps.inventory.models import StockBatch, StockItem
from apps.inventory.views import PharmacyViewSet
from apps.pos.models import Expense, ReturnRecord, Sale, SaleItem

from .models import CommissionConfig
from .serializers import CommissionConfigSerializer

MONEY = DecimalField(max_digits=16, decimal_places=2)
ZERO = Decimal("0.00")
REPORT_PERMISSIONS = [IsAuthenticated, IsTenantMember, IsPharmacyStaff]


def _money(expression):
    return ExpressionWrapper(expression, output_field=MONEY)


def _q(value):
    return Decimal(value or 0).quantize(Decimal("0.01"))


# --- date ranges ---------------------------------------------------------

def _period_range(period):
    """(start, end) for a named period, ending today."""
    today = timezone.localdate()
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=6), today
    if period == "quarter":
        return today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1), today
    if period == "year":
        return today.replace(month=1, day=1), today
    return today.replace(day=1), today  # default and "month"


def _resolve_range(request, default="month"):
    """Honour explicit ?from=&to=; else fall back to ?period=."""
    start_raw = request.query_params.get("from")
    end_raw = request.query_params.get("to")
    if start_raw and end_raw:
        try:
            start, end = date.fromisoformat(start_raw), date.fromisoformat(end_raw)
        except ValueError:
            raise ValidationError({"from": "Dates must be YYYY-MM-DD."})
        if start > end:
            start, end = end, start
        return "custom", start, end
    period = request.query_params.get("period", default)
    start, end = _period_range(period)
    return period, start, end


# --- shared money maths --------------------------------------------------

def _sales_in(start, end):
    """Sales made in a period that count as money earned."""
    return Sale.objects.filter(
        created_at__date__gte=start, created_at__date__lte=end,
        status__in=Sale.REVENUE_STATUSES,
    )


def _returns_in(start, end):
    """Refunds *recorded* in a period, whatever period their sale belongs to.

    Refunds against sales that never counted as revenue — a credit sale, a
    cancelled one — are skipped: subtracting them would push revenue below
    what was actually taken.
    """
    return ReturnRecord.objects.filter(
        created_at__date__gte=start, created_at__date__lte=end,
        sale__status__in=Sale.REVENUE_STATUSES,
    )


def _profit_figures(sales, returns):
    """Revenue, cost of goods and margin for a period, net of refunds."""
    gross = sales.aggregate(t=Sum("total"))["t"] or ZERO
    refunds = returns.aggregate(t=Sum("amount"))["t"] or ZERO
    revenue = _q(gross) - _q(refunds)

    agg = SaleItem.objects.filter(sale__in=sales).aggregate(
        cogs=Sum(_money(F("quantity") * F("cost_price")), filter=Q(cost_price__gt=0)),
        costed=Sum(_money(F("quantity") * F("unit_price")),
                   filter=Q(cost_price__gt=0)),
        line_total=Sum(_money(F("quantity") * F("unit_price"))),
    )
    # Cost of what came back, on the refund's own date. Lines with no cost
    # added none, so they subtract none.
    returned_cost = returns.aggregate(
        t=Sum(_money(F("quantity") * F("line__cost_price")),
              filter=Q(line__cost_price__gt=0))
    )["t"] or ZERO

    cogs = _q(agg["cogs"]) - _q(returned_cost)
    costed = _q(agg["costed"])
    line_total = _q(agg["line_total"])
    profit = revenue - cogs
    return {
        "revenue": revenue,
        "cost": cogs,
        "refunds": _q(refunds),
        "profit": profit,
        "margin": (round(float(profit / revenue * 100), 1) if revenue > 0 else 0.0),
        # Share of line revenue backed by a recorded cost. Below 1, the profit
        # figure is optimistic: the uncosted lines contribute no cost of goods.
        "cost_coverage": (round(float(costed / line_total), 4)
                          if line_total > 0 else 0.0),
    }


def _value_totals(qs):
    """Count, cost value and retail value across a batch queryset."""
    agg = qs.aggregate(
        cost=Sum(_money(F("quantity") * F("cost_price"))),
        retail=Sum(_money(F("quantity") * F("item__unit_price"))),
        units=Sum("quantity"),
    )
    return {
        "batches": qs.count(),
        "units": agg["units"] or 0,
        "cost_value": _q(agg["cost"]),
        "retail_value": _q(agg["retail"]),
    }


# --- reports -------------------------------------------------------------

@api_view(["GET"])
@permission_classes(REPORT_PERMISSIONS)
def sales_report(request):
    """What was sold over the period, and what money actually came in.

    ``payment_methods`` is money *received*, so it includes wallet top-ups —
    real cash across the counter — attributed to how they were funded. Wallet
    *spends* are deliberately absent: that money was already received when it
    was topped up, and counting it twice is the classic way this report goes
    wrong.
    """
    period, start, end = _resolve_range(request)

    everything = Sale.objects.filter(
        created_at__date__gte=start, created_at__date__lte=end
    ).exclude(status=Sale.Status.CANCELLED)
    credit = everything.filter(status=Sale.Status.CREDIT)
    sales = _sales_in(start, end)
    returns = _returns_in(start, end)

    def refunded(qs):
        return _q(qs.aggregate(t=Sum("amount"))["t"])

    retail_total = _q(sales.filter(is_wholesale=False).aggregate(
        t=Sum("total"))["t"]) - refunded(returns.filter(sale__is_wholesale=False))
    wholesale_total = _q(sales.filter(is_wholesale=True).aggregate(
        t=Sum("total"))["t"]) - refunded(returns.filter(sale__is_wholesale=True))

    # Units dispensed count every sale, credit included — that is what left the
    # shelf. Revenue per item counts only sales that earned money, so it
    # reconciles with the totals above.
    dispensed = {
        (r["item"], r["name"]): r["units"] or 0
        for r in SaleItem.objects.filter(sale__in=everything)
        .values("item", "name").annotate(units=Sum("quantity"))
    }
    revenue_by_item = {
        (r["item"], r["name"]): _q(r["revenue"])
        for r in SaleItem.objects.filter(sale__in=sales)
        .values("item", "name")
        .annotate(revenue=Sum(_money(F("quantity") * F("unit_price"))))
    }
    top_items = [
        {"item": item, "name": name or "Unknown", "units": units,
         "revenue": revenue_by_item.get((item, name), ZERO)}
        for (item, name), units in sorted(
            dispensed.items(), key=lambda kv: kv[1], reverse=True
        )[:10]
    ]

    daily = [
        {"date": str(r["day"]), "revenue": _q(r["revenue"]), "sales": r["n"]}
        for r in sales.annotate(day=TruncDate("created_at")).values("day")
        .annotate(revenue=Sum("total"), n=Count("id")).order_by("day")
    ]

    def topups_by_method(qs):
        buckets = {"cash": ZERO, "card": ZERO, "transfer": ZERO, "other": ZERO}
        for row in qs.values("method").annotate(t=Sum("amount")):
            key = row["method"] if row["method"] in buckets else "other"
            buckets[key] += _q(row["t"])
        return buckets

    topups = WalletTransaction.objects.filter(
        txn_type=WalletTransaction.Kind.TOPUP
    )
    period_topups = topups_by_method(
        topups.filter(created_at__date__gte=start, created_at__date__lte=end)
    )
    # Payments are read from the payment rows, not the sale's own method: a
    # card sale part-settled in cash put real notes in the drawer.
    taken = {
        row["method"]: _q(row["t"])
        for row in _payments_in(start, end).values("method").annotate(
            t=Sum("applied")
        )
    }
    payment_methods = {
        "cash": taken.get("cash", ZERO) + period_topups["cash"],
        "card": taken.get("card", ZERO) + period_topups["card"],
        "transfer": taken.get("transfer", ZERO) + period_topups["transfer"],
        # Wallet spends are not money received now; only the unattributed
        # top-ups sit here.
        "wallet": period_topups["other"],
    }

    expense_rows = Expense.objects.filter(date__gte=start, date__lte=end).values(
        "payment_source"
    ).annotate(t=Sum("amount"))
    expenses = {"cash": ZERO, "other": ZERO}
    for row in expense_rows:
        key = "cash" if row["payment_source"] == Expense.Source.CASH else "other"
        expenses[key] += _q(row["t"])
    expenses["total"] = expenses["cash"] + expenses["other"]

    revenue = retail_total + wholesale_total
    # Cash sold is what the drawer took less what it refunded; everything else
    # is derived from revenue, so the two halves always add back to the total.
    cash_sales = taken.get("cash", ZERO) - refunded(
        returns.filter(refund_method=ReturnRecord.RefundMethod.CASH)
    )
    other_sales = revenue - cash_sales

    return Response({
        "period": period,
        "date_from": str(start),
        "date_to": str(end),
        "total_revenue": revenue,
        "total_retail": retail_total,
        "total_wholesale": wholesale_total,
        "total_refunds": refunded(returns),
        "credit_sales": _q(credit.aggregate(t=Sum("total"))["t"]),
        "credit_count": credit.count(),
        "total_sales": sales.count(),
        "top_items": top_items,
        "daily": daily,
        "payment_methods": payment_methods,
        "expenses": expenses,
        "net": {
            "cash": cash_sales - expenses["cash"],
            "other": other_sales - expenses["other"],
            "total": revenue - expenses["total"],
        },
    })


def _payments_in(start, end):
    from apps.pos.models import SalePayment

    return SalePayment.objects.filter(
        created_at__date__gte=start, created_at__date__lte=end,
        sale__status__in=Sale.REVENUE_STATUSES,
    )


@api_view(["GET"])
@permission_classes(REPORT_PERMISSIONS)
def inventory_report(request):
    """What is on the shelf, what is about to be lost, and what already is.

    Expired stock is valued at cost — that is the money actually written off —
    with retail alongside it as what it would have fetched.
    """
    today = timezone.localdate()
    in_30 = today + timedelta(days=30)

    items = StockItem.objects.all()
    on_hand = StockBatch.objects.filter(quantity__gt=0)
    valuation = _value_totals(on_hand)

    low_stock = [
        {"item": i.pk, "name": i.name, "on_hand": i.quantity_on_hand,
         "reorder_level": i.reorder_level, "unit": i.unit}
        for i in items.filter(is_active=True)
        if i.quantity_on_hand <= i.reorder_level
    ][:50]

    expiring = on_hand.filter(expiry_date__gte=today, expiry_date__lte=in_30)
    expired = on_hand.filter(expiry_date__lt=today)

    def batch_rows(qs):
        return [
            {"batch": b.pk, "item": b.item_id, "name": b.item.name,
             "batch_number": b.batch_number, "quantity": b.quantity,
             "expiry_date": str(b.expiry_date),
             "cost_value": _q(b.quantity * b.cost_price),
             "retail_value": _q(b.quantity * b.item.unit_price),
             "days": (b.expiry_date - today).days}
            for b in qs.select_related("item").order_by("expiry_date")[:50]
        ]

    return Response({
        "total_items": items.count(),
        "active_items": items.filter(is_active=True).count(),
        "low_stock_count": len(low_stock),
        "low_stock": low_stock,
        **valuation,
        "expiring": _value_totals(expiring),
        "expiring_batches": batch_rows(expiring),
        "expired": _value_totals(expired),
        "expired_batches": batch_rows(expired),
    })


@api_view(["GET"])
@permission_classes(REPORT_PERMISSIONS)
def customer_report(request):
    """Who buys, who owes, and what the wallets are holding."""
    customers = Customer.objects.all()
    top = (Sale.objects.filter(customer__isnull=False,
                               status__in=Sale.REVENUE_STATUSES)
           .values("customer", "customer__name")
           .annotate(spent=Sum("total"), sales=Count("id"))
           .order_by("-spent")[:10])
    totals = customers.aggregate(
        wallets=Sum("wallet_balance"), debt=Sum("outstanding_debt")
    )
    return Response({
        "total": customers.count(),
        "retail": customers.filter(is_wholesale=False).count(),
        "wholesale": customers.filter(is_wholesale=True).count(),
        "wallet_balance": _q(totals["wallets"]),
        "outstanding_debt": _q(totals["debt"]),
        "top_customers": [
            {"customer": r["customer"], "name": r["customer__name"],
             "spent": _q(r["spent"]), "sales": r["sales"]}
            for r in top
        ],
    })


@api_view(["GET"])
@permission_classes(REPORT_PERMISSIONS)
def profit_report(request):
    """Revenue, cost of goods and margin over the period."""
    period, start, end = _resolve_range(request)
    figures = _profit_figures(_sales_in(start, end), _returns_in(start, end))
    return Response({
        "period": period,
        "date_from": str(start),
        "date_to": str(end),
        # True when nothing sold carried a cost price: the profit shown is just
        # the revenue, and says nothing useful yet.
        "estimated": figures["cost"] == ZERO,
        **figures,
    })


@api_view(["GET"])
@permission_classes(REPORT_PERMISSIONS)
def monthly_report(request):
    """One month of sales, day by day, zero-filled for charting."""
    today = timezone.localdate()
    try:
        year = int(request.query_params.get("year", today.year))
        month = int(request.query_params.get("month", today.month))
    except (TypeError, ValueError):
        raise ValidationError({"month": "Year and month must be whole numbers."})
    if not 1 <= month <= 12:
        raise ValidationError({"month": "Month must be between 1 and 12."})

    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    sales = _sales_in(start, end)
    by_day = {
        str(r["day"]): {"revenue": _q(r["revenue"]), "sales": r["n"]}
        for r in sales.annotate(day=TruncDate("created_at")).values("day")
        .annotate(revenue=Sum("total"), n=Count("id"))
    }
    series = []
    cursor = start
    while cursor <= end:
        series.append({"date": str(cursor),
                       **by_day.get(str(cursor), {"revenue": ZERO, "sales": 0})})
        cursor += timedelta(days=1)
    return Response({
        "year": year,
        "month": month,
        "total_revenue": _q(sales.aggregate(t=Sum("total"))["t"]),
        "total_sales": sales.count(),
        "daily": series,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsTenantMember, IsPharmacyStaff])
def cashier_sales_report(request):
    """Takings per person over the period, by how the money arrived.

    Anyone may read their own figures; only the pharmacy admin sees everyone's
    or filters to one member of staff — a shop-floor view of who took what is
    a performance record, not a dispensing tool.
    """
    period, start, end = _resolve_range(request, default="today")
    sales = _sales_in(start, end).filter(served_by__isnull=False)

    admin = is_pharmacy_admin(request.user)
    requested = request.query_params.get("user")
    if not admin:
        if requested and str(requested) != str(request.user.pk):
            raise PermissionDenied("You can only see your own takings.")
        sales = sales.filter(served_by=request.user)
        everyone = False
    elif requested:
        sales = sales.filter(served_by_id=requested)
        everyone = False
    else:
        everyone = True

    payments = _payments_in(start, end).filter(sale__in=sales)
    by_user_method = {}
    for row in payments.values("sale__served_by", "method").annotate(
        t=Sum("applied")
    ):
        by_user_method.setdefault(row["sale__served_by"], {})[row["method"]] = _q(
            row["t"]
        )

    rows = []
    total_amount = ZERO
    total_sales = 0
    for row in (sales.values("served_by", "served_by__username", "served_by__role")
                .annotate(amount=Sum("total"), n=Count("id"))
                .order_by("-amount")):
        amount = _q(row["amount"])
        total_amount += amount
        total_sales += row["n"]
        rows.append({
            "user": row["served_by"],
            "name": row["served_by__username"],
            "role": row["served_by__role"],
            "sales": row["n"],
            "amount": amount,
            "by_method": by_user_method.get(row["served_by"], {}),
        })

    return Response({
        "period": period,
        "date_from": str(start),
        "date_to": str(end),
        "all_staff": everyone,
        "total_amount": total_amount,
        "total_sales": total_sales,
        "staff": rows,
    })


@api_view(["GET"])
@permission_classes(REPORT_PERMISSIONS)
def staff_performance(request):
    """What each member of staff sold, and what that earns them.

    Staff with no commission row earn nothing rather than being left out: "sold
    a lot, paid nothing" is a fact worth seeing on the same page.
    """
    period, start, end = _resolve_range(request, default="month")
    sales = _sales_in(start, end).filter(served_by__isnull=False)
    configs = {
        c.user_id: c for c in CommissionConfig.objects.filter(is_active=True)
    }

    rows = []
    total_payout = ZERO
    for row in (sales.values("served_by", "served_by__username", "served_by__role")
                .annotate(amount=Sum("total"), n=Count("id"))
                .order_by("-amount")):
        amount = _q(row["amount"])
        config = configs.get(row["served_by"])
        rate = Decimal(config.rate) if config else ZERO
        bonus = _q(config.fixed_bonus) if config and config.fixed_bonus else ZERO
        earned = _q(amount * rate / Decimal("100"))
        payout = earned + bonus
        total_payout += payout
        rows.append({
            "user": row["served_by"],
            "name": row["served_by__username"],
            "role": row["served_by__role"],
            "sales": row["n"],
            "amount": amount,
            "rate": rate,
            "fixed_bonus": bonus,
            "commission": earned,
            "payout": payout,
        })

    return Response({
        "period": period,
        "date_from": str(start),
        "date_to": str(end),
        "total_payout": total_payout,
        "staff": rows,
    })


class CommissionConfigViewSet(PharmacyViewSet):
    """What each member of staff is paid on what they sell.

    Staff read the list — knowing your own rate is reasonable — but only the
    pharmacy admin sets one, because it is the pharmacy's money.
    """

    model = CommissionConfig
    serializer_class = CommissionConfigSerializer
    filterset_fields = ("user", "is_active")
    ordering_fields = ("rate",)

    def get_queryset(self):
        return CommissionConfig.objects.select_related("user")

    def _require_admin(self):
        if not is_pharmacy_admin(self.request.user):
            raise PermissionDenied(
                "Only the pharmacy admin can set commission rates."
            )

    def perform_create(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_update(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_admin()
        super().perform_destroy(instance)
