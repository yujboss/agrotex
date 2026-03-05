from django.db import models
from django.utils import timezone

# --- CONFIGURATION (Users & Stations) ---

class WorkStation(models.Model):
    name = models.CharField(max_length=50) # e.g. "Post 1"
    slug = models.SlugField(unique=True)
    ip_address = models.GenericIPAddressField(unique=True)
    is_active = models.BooleanField(default=True)
    
    # Brigadier PIN for this specific station (Simple security)
    reset_pin = models.CharField(max_length=4, default="1234", help_text="PIN to reset the truck")

    def __str__(self):
        return self.name

class Worker(models.Model):
    ROLE_CHOICES = [('USTA', 'Operator'), ('BRIGADIR', 'Brigadier')]
    
    name = models.CharField(max_length=100) # e.g. "Ali Valiyev"
    badge_id = models.CharField(max_length=20, unique=True) # e.g. "USTA_1"
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='USTA')
    
    # Assign worker to a station (Optional: can be null if they roam)
    assigned_station = models.ForeignKey(WorkStation, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.badge_id})"

# --- STATIC DATA (The Plan) ---

class ProductVariant(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    image = models.ImageField(upload_to='trucks/', blank=True, null=True)
    def __str__(self): return self.name

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
    workstation = models.ForeignKey(WorkStation, on_delete=models.CASCADE)
    product = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    category = models.ForeignKey(TaskCategory, on_delete=models.CASCADE, null=True, blank=True)
    
    step_number = models.IntegerField()
    description = models.TextField()
    standard_duration_seconds = models.IntegerField(default=300)
    tooling = models.CharField(max_length=200, blank=True)
    torque = models.CharField(max_length=50, blank=True)
    
    class Meta:
        ordering = ['step_number']
        unique_together = ('workstation', 'product', 'step_number')

    def __str__(self):
        return f"Step {self.step_number}: {self.description}"

# --- DYNAMIC DATA (The Reality) ---

class TruckRun(models.Model):
    workstation = models.ForeignKey(WorkStation, on_delete=models.CASCADE)
    product = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    # Same VIN can appear at multiple posts as the truck moves down the line
    truck_serial_number = models.CharField(max_length=100, null=True, blank=True)
    start_time = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

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