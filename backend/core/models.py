from django.db import models
from django.utils import timezone

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
        return self.truck_serial_number


class TaskLog(models.Model):
    STATUS_COLORS = [
        ('GREEN', 'On Time'),
        ('YELLOW', 'Late'),
        ('RED', 'Very Late / Issue'),
    ]

    truck_run = models.ForeignKey(TruckRun, on_delete=models.CASCADE, related_name='logs')
    assembly_step = models.ForeignKey(AssemblyStep, on_delete=models.CASCADE)
    operator = models.ForeignKey(Worker, on_delete=models.SET_NULL, null=True) # Link to real Worker model
    
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    was_intervened = models.BooleanField(default=False)
    
    # We store the final status color for easy querying
    status_color = models.CharField(max_length=10, choices=STATUS_COLORS, null=True, blank=True)

    class Meta:
        ordering = ['start_time']