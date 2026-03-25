from django.contrib import admin
from django.utils.html import format_html
from .models import StepPart
from .models import PurchaseOrder
from django.forms import Textarea
from django.db import models
from .models import AssemblyStep, StepPart, Part
admin.site.register(PurchaseOrder)

from .models import (
    WorkStation,
    Worker,
    ProductVariant,
    TaskCategory,
    AssemblyStep,
    TruckRun,
    TaskLog,
    Order,
    Part,
    Inventory,
    PartConsumption
)

admin.site.register(StepPart)

# -------------------------------
# Worker
# -------------------------------

@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ('name', 'badge_id', 'role', 'assigned_station', 'show_photo')
    # --- НОВАЯ СТРОЧКА ---
    change_form_template = 'face/change_form.html'
    def show_photo(self, obj):
        if obj.photo:
            return format_html('<img src="{}" width="40" height="40" style="border-radius:50%; object-fit:cover;" />', obj.photo.url)
        return "No Photo"
    show_photo.short_description = 'Avatar'

# -------------------------------
# Order
# -------------------------------

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'quantity', 'delivery_date', 'created_at')


# -------------------------------
# Parts / Warehouse
# -------------------------------

# Обязательно добавляем поиск по деталям
@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'unit')
    search_fields = ('code', 'name') # Включает поиск

# Таблица добавления деталей внутрь Задания
class StepPartInline(admin.TabularInline):
    model = StepPart
    extra = 1
    autocomplete_fields = ['part'] # Включает умный выпадающий список

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('part', 'quantity', 'location', 'updated_at')


@admin.register(PartConsumption)
class PartConsumptionAdmin(admin.ModelAdmin):
    list_display = ('part', 'truck_run', 'assembly_step', 'quantity', 'consumed_at')


# -------------------------------
# Task Category
# -------------------------------

@admin.register(TaskCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'ordering')


# -------------------------------
# Assembly Steps
# -------------------------------

@admin.register(AssemblyStep)
class AssemblyStepAdmin(admin.ModelAdmin):
    list_display = ('product', 'step_number', 'workstation', 'heading', 'standard_duration_seconds')
    list_filter = ('product', 'workstation')
    search_fields = ('heading', 'description')
    
    formfield_overrides = {
        models.TextField: {'widget': Textarea(attrs={'rows': 4, 'cols': 60})},
    }
    
    inlines = [StepPartInline]

@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    # Добавляем колонку 'barcode_preview' в список
    list_display = ('code', 'name', 'unit', 'barcode_preview')
    search_fields = ('code', 'name')

    # Функция, которая рисует картинку штрих-кода (формат Code128 поддерживает буквы и цифры)
    def barcode_preview(self, obj):
        if obj.code:
            # Генерируем картинку налету
            url = f"https://barcode.tec-it.com/barcode.ashx?data={obj.code}&code=Code128&dpi=96"
            return format_html('<img src="{}" height="40" style="border: 1px solid #ccc; padding: 2px; background: white;">', url)
        return "-"
    
    barcode_preview.short_description = "Штрих-код"




@admin.register(DefectLog)
class DefectLogAdmin(admin.ModelAdmin):
    # Какие колонки показывать в таблице
    list_display = ('truck_run', 'category', 'worker', 'is_critical', 'is_resolved', 'reported_at')
    # Фильтры сбоку (очень удобно искать критические)
    list_filter = ('is_critical', 'is_resolved', 'category')
    # Поиск по VIN-номеру трактора
    search_fields = ('truck_run__truck_serial_number', 'description')


# -------------------------------
# Product Variant
# -------------------------------

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'image_preview')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:100px;max-width:100px;" />',
                obj.image.url
            )
        return "No image"

    image_preview.short_description = 'Image Preview'


# -------------------------------
# Simple registrations
# -------------------------------

admin.site.register(WorkStation)
admin.site.register(TruckRun)
admin.site.register(TaskLog)