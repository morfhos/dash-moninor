from django.contrib import admin

from .models import (
    Campaign,
    ContractUpload,
    CreativeAsset,
    MediaPlanUpload,
    Piece,
    PlacementCreative,
    PlacementDay,
    PlacementLine,
)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "cliente", "media_type", "start_date", "end_date", "status", "created_by", "updated_at")
    list_filter = ("status", "cliente", "media_type")
    search_fields = ("name", "cliente__nome")


@admin.register(Piece)
class PieceAdmin(admin.ModelAdmin):
    list_display = ("campaign", "code", "title", "type", "status", "duration_sec", "created_at")
    list_filter = ("type", "status", "campaign")
    search_fields = ("code", "title")


@admin.register(PlacementLine)
class PlacementLineAdmin(admin.ModelAdmin):
    list_display = (
        "campaign",
        "media_type",
        "media_channel",
        "market",
        "channel",
        "program",
        "start_date",
        "end_date",
        "duration_sec",
        "external_ref",
        "created_at",
    )
    list_filter = ("media_type", "media_channel", "market", "campaign")
    search_fields = ("market", "channel", "program", "property_text", "format_text", "external_ref")


@admin.register(PlacementDay)
class PlacementDayAdmin(admin.ModelAdmin):
    list_display = ("placement_line", "date", "insertions", "cost", "impressions", "clicks")
    list_filter = ("date",)


@admin.register(CreativeAsset)
class CreativeAssetAdmin(admin.ModelAdmin):
    list_display = ("piece", "file", "checksum", "created_at")
    search_fields = ("file", "preview_url", "thumb_url", "checksum")


@admin.register(ContractUpload)
class ContractUploadAdmin(admin.ModelAdmin):
    list_display = ("campaign", "file", "created_at")


@admin.register(MediaPlanUpload)
class MediaPlanUploadAdmin(admin.ModelAdmin):
    list_display = ("campaign", "file", "created_at")


@admin.register(PlacementCreative)
class PlacementCreativeAdmin(admin.ModelAdmin):
    list_display = ("placement_line", "piece", "weight", "created_at")
