from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from .models import WorkStation, AssemblyStep, ProductVariant, TruckRun, Worker, TaskLog
import logging
from core.telegram_bot import send_telegram_message
from .models import Inventory
from django.shortcuts import render, redirect
from core.models import Worker
from django.http import HttpResponseForbidden
from core.models import Worker, Inventory
from django.shortcuts import render, redirect
from .models import ProductionOrder, TruckRun, ProductVariant
from django.views.decorators.csrf import csrf_exempt
from .models import ProductionOrder, ProductVariant, TruckRun
from .models import ProductionOrder
from django.http import HttpResponseForbidden
from core.models import Worker, Inventory

logger = logging.getLogger(__name__)

def login_page(request):

    if request.method == "POST":

        badge = request.POST.get("badge")

        worker = Worker.objects.filter(badge_id=badge).first()

        if not worker:
            return render(request, "login.html", {"error": "Worker not found"})

        request.session["worker_badge"] = worker.badge_id

        if worker.role == "WAREHOUSE":
            return redirect("/warehouse/")

        if worker.role == "BRIGADIR":
            return redirect("/dashboard/")
        if worker.role == "ORDER_MANAGER":
            return redirect("/orders/")
        if worker.role == "USTA":
            return redirect(f"/station/{worker.assigned_station.slug}/")

    return render(request, "login.html")


def get_client_ip(request):
    """Get the client's IP address, considering proxies (X-Forwarded-For)."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # First IP in the list is the original client (others are proxies)
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def get_station_for_request(request):
    """
    Resolve the WorkStation for this request based on the client's IP address.
    Returns the station whose ip_address matches the client IP, or None if no match.
    """
    client_ip = get_client_ip(request)
    if not client_ip:
        return None
    return WorkStation.objects.filter(is_active=True, ip_address=client_ip).first()


SESSION_STATION_SLUG_KEY = 'selected_station_slug'


def get_station_from_session(request):
    """Get the WorkStation stored in session (manual selection). Returns None if not set."""
    slug = request.session.get(SESSION_STATION_SLUG_KEY)
    if not slug:
        return None
    return WorkStation.objects.filter(is_active=True, slug=slug).first()


def station_picker(request):
    """Let the user choose which station (Post 1, Post 2, etc.) this client is."""
    stations = WorkStation.objects.filter(is_active=True).order_by('name')[:12]
    if request.method == 'POST':
        slug = request.POST.get('station_slug')
        # Validate against base queryset (cannot filter a sliced queryset)
        if slug and WorkStation.objects.filter(is_active=True, slug=slug).exists():
            request.session[SESSION_STATION_SLUG_KEY] = slug
            return redirect('truck_selection')
    context = {'stations': stations}
    return render(request, 'core/station_picker.html', context)


def station_picker_clear(request):
    """Clear the selected station from session and redirect to station picker."""
    if SESSION_STATION_SLUG_KEY in request.session:
        del request.session[SESSION_STATION_SLUG_KEY]
    return redirect('station_picker')


def truck_selection(request):
    products = ProductVariant.objects.all()

    station = get_station_from_session(request)
    if not station:
        return redirect('station_picker')

    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        truck_serial_number = request.POST.get('truck_serial_number')

        product = get_object_or_404(ProductVariant, id=product_id)

        # 1️⃣ если трактор с таким VIN уже есть → открыть его станцию
        existing_run = TruckRun.objects.filter(
            truck_serial_number=truck_serial_number,
            is_active=True
        ).first()

        if existing_run:
            return redirect('station_detail', slug=existing_run.workstation.slug)

        # 2️⃣ если на станции уже есть трактор → НЕ менять его
        station_run = TruckRun.objects.filter(
            workstation=station,
            is_active=True
        ).first()

        if station_run:
            return redirect('station_detail', slug=station.slug)

        # 3️⃣ создать новый трактор
        TruckRun.objects.create(
            workstation=station,
            product=product,
            truck_serial_number=truck_serial_number,
            is_active=True
        )

        return redirect('station_detail', slug=station.slug)

    context = {
        'products': products,
        'station': station,
        'media_url': settings.MEDIA_URL,
        'media_root': str(settings.MEDIA_ROOT),
    }

    return render(request, 'core/truck_selection.html', context)

def station_detail(request, station_slug):

    station = get_object_or_404(WorkStation, slug=station_slug)

    available_trucks = TruckRun.objects.filter(
        workstation=station,
        is_active=False
    )

    return render(request, "core/station_detail.html", {
        "station": station,
        "available_trucks": available_trucks
    })

def production_dashboard(request):
    """Production line dashboard showing all stations"""
    stations = WorkStation.objects.filter(is_active=True).order_by('name')[:12]
    context = {
        'stations': stations,
    }
    return render(request, 'core/production_dashboard.html', context)


def run_page(request):
    """Display the production run table (run.html data)."""
    return render(request, 'core/run.html')
    





def warehouse_dashboard(request):

    badge = request.session.get("worker_badge")

    worker = Worker.objects.filter(badge_id=badge).first()

    if not worker or worker.role != "WAREHOUSE":
        return HttpResponseForbidden("Access denied")

    inventory = Inventory.objects.select_related("part").all()

    data = []

    for item in inventory:

        status = item.stock_status()

        if status == "RED":
            color = "critical"
        elif status == "YELLOW":
            color = "low"
        else:
            color = "ok"

        data.append({
            "part": item.part.code,
            "stock": item.quantity,
            "status": status,
            "color": color
        })

    return render(request, "warehouse/dashboard.html", {
        "inventory": data
    })










def create_production_order(request):
    if request.method == "POST":
        product_id = request.POST.get("product_id")
        quantity = int(request.POST.get("quantity", 1))
        vin_prefix = request.POST.get("vin_prefix")

        # ИСПОЛЬЗУЕМ ТВОЙ PRODUCT VARIANT
        selected_product = get_object_or_404(ProductVariant, id=product_id)

        order = ProductionOrder.objects.create(
            model_name=selected_product.name, 
            quantity=quantity,
            vin_prefix=vin_prefix,
            tractor_image=selected_product.image 
        )

        first_station = WorkStation.objects.filter(is_active=True).order_by("id").first()

        for i in range(quantity):
            if quantity == 1:
                serial = vin_prefix
            else:
                serial = f"{vin_prefix}{str(i+1).zfill(3)}"

            TruckRun.objects.create(
                workstation=first_station,
                product=selected_product, 
                truck_serial_number=serial,
                is_active=False
            )

        return redirect("/orders/")

    # Передаем ProductVariant в выпадающий список
    products = ProductVariant.objects.all()
    return render(request, "orders/create_order.html", {"products": products})


def orders_page(request):
    orders = ProductionOrder.objects.all().order_by("-id")
    products = ProductVariant.objects.all() # Берем ProductVariant

    return render(request, "orders/orders.html", {
        "orders": orders,
        "products": products 
    })


def delete_order(request, id):

    order = ProductionOrder.objects.get(id=id)

    order.delete()

    return redirect("/orders/")