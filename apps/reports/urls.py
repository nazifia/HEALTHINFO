from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("reports/commission-configs", views.CommissionConfigViewSet,
                basename="commission-config")

urlpatterns = [
    path("reports/sales/", views.sales_report, name="report-sales"),
    path("reports/inventory/", views.inventory_report, name="report-inventory"),
    path("reports/customers/", views.customer_report, name="report-customers"),
    path("reports/profit/", views.profit_report, name="report-profit"),
    path("reports/monthly/", views.monthly_report, name="report-monthly"),
    path("reports/cashier-sales/", views.cashier_sales_report,
         name="report-cashier-sales"),
    path("reports/staff-performance/", views.staff_performance,
         name="report-staff-performance"),
] + router.urls
