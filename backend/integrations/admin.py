from django.contrib import admin

from .models import GoogleAdsAccount, SyncLog, MetaAdsAccount, MetaSyncLog


@admin.register(GoogleAdsAccount)
class GoogleAdsAccountAdmin(admin.ModelAdmin):
    list_display = ("cliente", "customer_id", "descriptive_name", "is_active", "last_sync")
    list_filter = ("is_active",)
    search_fields = ("customer_id", "descriptive_name", "cliente__nome")


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("account", "started_at", "finished_at", "status", "campaigns_synced", "metrics_synced")
    list_filter = ("status",)


@admin.register(MetaAdsAccount)
class MetaAdsAccountAdmin(admin.ModelAdmin):
    list_display = ("cliente", "ad_account_id", "descriptive_name", "is_active", "last_sync")
    list_filter = ("is_active",)
    search_fields = ("ad_account_id", "descriptive_name", "cliente__nome")


@admin.register(MetaSyncLog)
class MetaSyncLogAdmin(admin.ModelAdmin):
    list_display = ("account", "started_at", "finished_at", "status", "campaigns_synced", "metrics_synced")
    list_filter = ("status",)
