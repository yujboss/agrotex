from django.db import models
from django.utils import timezone
import qrcode
from io import BytesIO
from django.core.files import File


# --- CONFIGURATION (Users & Stations) ---

class WorkStation(models.Model):
    name = models.CharField(max_length=50)  # e.g. "Post 1"
    slug = models.SlugField(unique=True)
    ip_address = models.GenericIPAddressField(unique=True)
    is_active = models.BooleanField(default=True)

    # Brigadier PIN for this specific station
    reset_pin = models.CharField(
        max_length=4,
        default="1234",
        help_text="PIN to reset the truck"
    )

    def __str__(self):
        return self.name


class Worker(models.Model):
    ROLE_CHOICES = [
        ('USTA', 'Operator'),
        ('BRIGADIR', 'Brigadier'),
        ("WAREHOUSE","Warehouse"),
        ('ORDER_MANAGER', 'Order Manager')
    ]

    # НОВОЕ ПОЛЕ ДЛЯ ЗАМЕН:
    is_substitute = models.BooleanField(default=False, verbose_name="Рабочий на замену (скрыть из списка станции)")

    substituted_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, 
        related_name='substituting_for', verbose_name="Кем заменен в данный момент"
    )

    name = models.CharField(max_length=100)  # e.g. "Ali Valiyev"
    badge_id = models.CharField(max_length=20, unique=True)  # e.g. "USTA_1"
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='USTA')
    # Мы будем хранить здесь массив координат лица (128 точек)
    face_descriptor = models.JSONField(null=True, blank=True, verbose_name="Цифровой отпечаток лица")
    assigned_station = models.ForeignKey(
        WorkStation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # NEW FIELD → QR CODE
    qr_code = models.ImageField(upload_to="qr_codes/", blank=True, null=True)

    # --- НОВОЕ ПОЛЕ: ФОТО СОТРУДНИКА ---
    photo = models.ImageField(upload_to="worker_photos/", blank=True, null=True, verbose_name="Фото сотрудника")

    def save(self, *args, **kwargs):
        if not self.qr_code:
            qr = qrcode.make(self.badge_id)

            buffer = BytesIO()
            qr.save(buffer, format="PNG")

            file_name = f"{self.badge_id}.png"
            self.qr_code.save(file_name, File(buffer), save=False)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.badge_id})"


# --- STATIC DATA (The Plan) ---

class ProductVariant(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    image = models.ImageField(upload_to='trucks/', blank=True, null=True)

    def __str__(self):
        return self.name


class TaskCategory(models.Model):
    """ Grouping steps (e.g. '1. Marking', '2. Chassis Assembly') """

    name = models.CharField(max_length=100)
    ordering = models.IntegerField(default=0)

    class Meta:
        ordering = ['ordering']
        verbose_name_plural = "Task Categories"

    def __str__(self):
        return self.name


class AssemblyStep(models.Model):
    workstation = models.ForeignKey('WorkStation', on_delete=models.CASCADE)
    
    # Привязка к трактору
    product = models.ForeignKey('ProductVariant', on_delete=models.CASCADE, null=True, blank=True)
    category = models.ForeignKey('TaskCategory', on_delete=models.CASCADE, null=True, blank=True)
    
    step_number = models.IntegerField("№ шага")
    
    # Тот самый заголовок
    heading = models.CharField("Заголовок (например: 1.1 Установка...)", max_length=255, blank=True, null=True)
    
    description = models.TextField("Описание работ")
    standard_duration_seconds = models.IntegerField("Время (сек)", default=300)

    tooling = models.CharField("Оснастка", max_length=200, blank=True)
    torque = models.CharField("Момент затяжки", max_length=50, blank=True)

    class Meta:
        ordering = ['product', 'step_number']
        unique_together = ('product', 'workstation', 'step_number')
        
        verbose_name = "Задание"
        verbose_name_plural = "Задания (Техкарты)"

    def __str__(self):
        return f"{self.product} | Шаг {self.step_number}"


# --- DYNAMIC DATA (The Reality) ---

class TruckRun(models.Model):
    # --- НОВЫЕ СТАТУСЫ ДЛЯ ТРАКТОРА ---
    STATUS_CHOICES = [
        ('IN_PROGRESS', 'В процессе сборки'),
        ('REWORK', 'На доработке (Брак)'),
        ('COMPLETED', 'Сборка завершена'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_PROGRESS')
    # ----------------------------------

    product = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    workstation = models.ForeignKey(
        WorkStation,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    truck_serial_number = models.CharField(max_length=100, unique=True)
    current_station = models.IntegerField(default=1)
    start_time = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False)
    is_finished = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.truck_serial_number} ({self.get_status_display()})"


class DefectLog(models.Model):
    # Категории дефектов для удобной статистики
    DEFECT_CATEGORIES = [
        ('MECH', 'Механический дефект (резьба, металл)'),
        ('ELEC', 'Электрика (проводка, контакты)'),
        ('PAINT', 'Покраска / Царапины'),
        ('PART_MISSING', 'Нехватка детали / Недокомплект'),
        ('PART_DEFECT', 'Брак самой детали'),
        ('OTHER', 'Другое'),
    ]

    # Привязка к конкретному физическому трактору
    truck_run = models.ForeignKey(TruckRun, on_delete=models.CASCADE, related_name='defects', verbose_name="Трактор (VIN)")
    
    # На каком шаге нашли проблему
    assembly_step = models.ForeignKey(AssemblyStep, on_delete=models.CASCADE, verbose_name="Шаг сборки")
    
    # Кто именно сообщил о браке
    worker = models.ForeignKey(Worker, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Сотрудник")
    
    # Суть проблемы (Dropdown + Текст от рабочего)
    category = models.CharField("Категория", max_length=20, choices=DEFECT_CATEGORIES, default='OTHER')
    description = models.TextField("Описание дефекта (текст)")
    
    # Логика блокировки
    is_critical = models.BooleanField("Критический (Блокирует конвейер)", default=False)
    
    # Статус исправления (чтобы мастер мог закрыть дефект)
    is_resolved = models.BooleanField("Исправлено", default=False)
    
    # Тайминги
    reported_at = models.DateTimeField("Время обнаружения", auto_now_add=True)
    resolved_at = models.DateTimeField("Время устранения", null=True, blank=True)

    class Meta:
        verbose_name = "Журнал дефектов"
        verbose_name_plural = "Журнал дефектов"
        ordering = ['-reported_at']

    def __str__(self):
        crit = "🔴 КРИТИЧЕСКИЙ" if self.is_critical else "🟡 МЕЛКИЙ"
        resolved = "✅ Закрыт" if self.is_resolved else "❌ Активен"
        return f"{crit} | {self.truck_run.truck_serial_number} | {self.get_category_display()} [{resolved}]"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Если это критический дефект, и его только что пометили как "Исправлено"
        if self.is_critical and self.is_resolved:
            # Проверяем, остались ли на этом тракторе другие неисправленные критические дефекты
            unresolved_criticals = DefectLog.objects.filter(
                truck_run=self.truck_run, 
                is_critical=True, 
                is_resolved=False
            ).exists()
            
            # Если других проблем нет — РАЗБЛОКИРУЕМ КОНВЕЙЕР!
            if not unresolved_criticals:
                self.truck_run.status = 'IN_PROGRESS'
                self.truck_run.save()

class TaskLog(models.Model):

    STATUS_COLORS = [
        ('GREEN', 'On Time'),
        ('YELLOW', 'Late'),
        ('RED', 'Very Late / Issue'),
    ]

    truck_run = models.ForeignKey(
        TruckRun,
        on_delete=models.CASCADE,
        related_name='logs'
    )

    assembly_step = models.ForeignKey(AssemblyStep, on_delete=models.CASCADE)

    operator = models.ForeignKey(
        Worker,
        on_delete=models.SET_NULL,
        null=True
    )

    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    was_intervened = models.BooleanField(default=False)

    status_color = models.CharField(
        max_length=10,
        choices=STATUS_COLORS,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['start_time']

class Order(models.Model):

    customer = models.CharField(max_length=200)

    delivery_date = models.DateField()

    product = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)

    quantity = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    is_planned = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.customer} - {self.product.name} ({self.quantity})"        
    


class Part(models.Model):

    code = models.CharField(max_length=50, unique=True)

    name = models.CharField(max_length=200)
    reorder_level = models.IntegerField(default=10)

    reorder_quantity = models.IntegerField(default=20)
    unit = models.CharField(max_length=20, default="pcs")

    def __str__(self):
        return f"{self.code} - {self.name}"


class Inventory(models.Model):

    part = models.ForeignKey(Part, on_delete=models.CASCADE)

    quantity = models.PositiveIntegerField(default=0)

    location = models.CharField(max_length=100, default="Main Warehouse")

    updated_at = models.DateTimeField(auto_now=True)

    low_level = models.IntegerField(default=5)

    critical_level = models.IntegerField(default=2)

    def stock_status(self):

        if self.quantity <= self.critical_level:
            return "RED"

        if self.quantity <= self.low_level:
            return "YELLOW"

        return "GREEN"

    def __str__(self):
        return f"{self.part.code} ({self.quantity})"


class PartConsumption(models.Model):

    part = models.ForeignKey(Part, on_delete=models.CASCADE)

    truck_run = models.ForeignKey(TruckRun, on_delete=models.CASCADE)

    assembly_step = models.ForeignKey(AssemblyStep, on_delete=models.CASCADE)

    quantity = models.IntegerField()

    consumed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.part.code} used in {self.truck_run.id}"  



class StepPart(models.Model):
    assembly_step = models.ForeignKey(
        AssemblyStep,
        on_delete=models.CASCADE,
        related_name="required_parts"
    )
    part = models.ForeignKey(
        Part,
        on_delete=models.CASCADE
    )
    quantity = models.IntegerField(default=1)
    
    # --- НОВОЕ ПОЛЕ: Номер пакета (из Excel) ---
    package_number = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        verbose_name="№ пакета"
    )

    def __str__(self):
        return f"{self.assembly_step} → {self.part.code} x{self.quantity}"          


class PurchaseOrder(models.Model):

    part = models.ForeignKey(Part, on_delete=models.CASCADE)

    quantity = models.IntegerField()

    status = models.CharField(
        max_length=20,
        default="PENDING"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PO - {self.part.code} ({self.quantity})"



class ProductionOrder(models.Model):

    model_name = models.CharField(max_length=200, default="Unknown")

    quantity = models.IntegerField()

    vin_prefix = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    tractor_image = models.ImageField(
        upload_to="tractors/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.model_name} x{self.quantity}"
