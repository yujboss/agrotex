from django.contrib import admin
from django.utils.html import format_html
from .models import WorkStation, Worker, ProductVariant, TaskCategory, AssemblyStep, TruckRun, TaskLog

@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ('name', 'badge_id', 'role', 'assigned_station')

@admin.register(TaskCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'ordering')

@admin.register(AssemblyStep)
class AssemblyStepAdmin(admin.ModelAdmin):
    list_display = ('step_number', 'category', 'description', 'workstation')
    list_filter = ('workstation', 'category')

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'image_preview')
    readonly_fields = ('image_preview',)
    
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 100px; max-width: 100px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Image Preview'

admin.site.register(WorkStation)
admin.site.register(TruckRun)
admin.site.register(TaskLog)