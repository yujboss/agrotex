from django.contrib import admin
from django.utils.html import format_html
from .models import StepPart
from .models import PurchaseOrder
from django.forms import Textarea
from django.db import models
from .models import AssemblyStep, StepPart, Part
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from .models import DefectLog
from django.contrib import admin
from django.utils.html import format_html
from .models import Part
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
    change_form_template = 'face/change_form.html'

    def show_photo(self, obj):
        if obj.photo:
            return format_html('<img src="{}" width="40" height="40" style="border-radius:50%; object-fit:cover;" />', obj.photo.url)
        return "No Photo"
    show_photo.short_description = 'Avatar'

    # --- 1. Добавляем URL для кнопки замены ---
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:worker_id>/substitute/', self.admin_site.admin_view(self.substitute_worker), name='substitute-worker'),
            path('<int:worker_id>/revert/', self.admin_site.admin_view(self.revert_substitute), name='revert-substitute'), # <--- НОВАЯ СТРОЧКА
        ]
        return custom_urls + urls

    # --- 2. Передаем список других рабочих в шаблон админки ---
    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            # Убрали фильтр по станции, чтобы можно было выбрать любого рабочего на замену
            extra_context['other_workers'] = Worker.objects.exclude(id=object_id)
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    # --- 3. Сама логика передачи задач ---
    def substitute_worker(self, request, worker_id):
        if request.method == 'POST':
            new_worker_id = request.POST.get('new_worker_id')
            if not new_worker_id:
                messages.error(request, "Ошибка: Вы не выбрали рабочего на замену!")
                return redirect('admin:core_worker_change', worker_id)

            sick_worker = Worker.objects.get(id=worker_id)
            new_worker = Worker.objects.get(id=new_worker_id)

            # 1. ЗАПИСЫВАЕМ СВЯЗЬ В БАЗУ (Это скрывает больного с экрана!)
            sick_worker.substituted_by = new_worker
            sick_worker.save()

            # 2. Переводим временного рабочего на эту станцию
            if sick_worker.assigned_station:
                new_worker.assigned_station = sick_worker.assigned_station
                new_worker.is_substitute = True
                new_worker.save()

            # 3. Передаем активные задачи
            incomplete_tasks = TaskLog.objects.filter(operator=sick_worker, end_time__isnull=True)
            for task in incomplete_tasks:
                task.operator = new_worker
                task.was_intervened = True
                task.save()
                
            messages.success(request, f"✅ Рабочий {sick_worker.name} скрыт. Его заменяет {new_worker.name}!")

        return redirect('admin:core_worker_change', worker_id)

    # --- 4. КНОПКА ОТМЕНЫ ЗАМЕНЫ ---
    def revert_substitute(self, request, worker_id):
        if request.method == 'POST':
            sick_worker = Worker.objects.get(id=worker_id)
            sub = sick_worker.substituted_by # Находим его замену
            
            if sub:
                # Возвращаем активные задачи обратно больному
                tasks = TaskLog.objects.filter(operator=sub, end_time__isnull=True, was_intervened=True)
                for t in tasks:
                    t.operator = sick_worker
                    t.was_intervened = False
                    t.save()
                
                # Убираем временного рабочего со станции
                sub.assigned_station = None
                sub.is_substitute = False
                sub.save()

                # Отвязываем замену
                sick_worker.substituted_by = None
                sick_worker.save()
                
                messages.success(request, f"✅ Замена отменена. {sick_worker.name} вернулся на станцию.")
            else:
                messages.error(request, "Этот рабочий сейчас никем не заменяется.")
                
        return redirect('admin:core_worker_change', worker_id)

# -------------------------------
# Order
# -------------------------------

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product', 'quantity', 'delivery_date', 'created_at')


# -------------------------------
# Parts / Warehouse
# -------------------------------



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