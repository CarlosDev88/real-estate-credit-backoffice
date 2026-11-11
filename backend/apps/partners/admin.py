from django.contrib import admin

from apps.partners.models import Partner, PartnerMembership, Project


class PartnerMembershipInline(admin.TabularInline):
    model = PartnerMembership
    extra = 0
    autocomplete_fields = ["user"]
    fields = ["user", "job_title", "status", "started_at", "ended_at"]


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ["legal_name", "trade_name", "tax_id", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["legal_name", "trade_name", "tax_id"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [PartnerMembershipInline]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "partner", "status", "city_item", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "code", "address"]
    autocomplete_fields = ["partner", "city_item", "created_by", "validated_by"]
    readonly_fields = ["created_at", "updated_at", "validated_at"]


@admin.register(PartnerMembership)
class PartnerMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "partner", "status", "started_at", "ended_at"]
    list_filter = ["status"]
    search_fields = ["user__email", "partner__legal_name"]
    autocomplete_fields = ["user", "partner"]
