from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.shortcuts import get_object_or_404
from datetime import datetime, timezone as dt_timezone
from django.http import JsonResponse
from django.utils import timezone
from core.telegram_bot import send_telegram_message
from .models import Worker
import json
from .models import WorkStation, Worker, TruckRun, TaskLog, AssemblyStep
from .models import StepPart, Inventory, PartConsumption
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from core.models import Part, Order
from core.models import PurchaseOrder

@csrf_exempt
def next_task_api(request, station_slug):
    """ Handles Space Bar: Closes current task, starts the next one """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        worker_badge = data.get('operator_id')
        station = get_object_or_404(WorkStation, slug=station_slug)
        worker = Worker.objects.filter(badge_id=worker_badge).first()

        if not worker:
            return JsonResponse({'error': 'worker_not_found'})

        # Ищем активный трактор именно по current_station
        truck_run = TruckRun.objects.filter(
            current_station=station.id,
            is_active=True
        ).last()

        if not truck_run:
            return JsonResponse({'status': 'no_truck'})

        # Загружаем шаги для этой станции
        steps = AssemblyStep.objects.filter(workstation=station).order_by('step_number')
        active_task = TaskLog.objects.filter(truck_run=truck_run, end_time__isnull=True).first()

        if active_task:
            active_task.end_time = timezone.now()
            
            # --- Логика списания деталей (Backflush) ---
            step_parts = StepPart.objects.filter(assembly_step=active_task.assembly_step)
            for sp in step_parts:
                inventory = Inventory.objects.filter(part_id=sp.part_id).first()
                if inventory and inventory.quantity >= sp.quantity:
                    inventory.quantity -= sp.quantity
                    inventory.save()
                    
                    # Telegram Alerts
                    status = inventory.stock_status()
                    if status in ["YELLOW", "RED"]:
                        msg = f"{'🚨 CRITICAL' if status == 'RED' else '⚠ LOW'} STOCK\nPart: {inventory.part.code}\nStation: {station.name}"
                        send_telegram_message(msg)
                    
                    PartConsumption.objects.create(
                        part=sp.part, truck_run=truck_run, 
                        assembly_step=active_task.assembly_step, quantity=sp.quantity
                    )

            # Расчет цвета (G/Y/R)
            duration = (active_task.end_time - active_task.start_time).total_seconds()
            std_time = active_task.assembly_step.standard_duration_seconds or 180
            if duration <= std_time: active_task.status_color = 'GREEN'
            elif duration <= std_time * 1.2: active_task.status_color = 'YELLOW'
            else: active_task.status_color = 'RED'
            active_task.save()
            
            last_step_num = active_task.assembly_step.step_number
        else:
            # Если активных задач нет, смотрим последнюю завершенную
            last_done = TaskLog.objects.filter(truck_run=truck_run, end_time__isnull=False).order_by('end_time').last()
            last_step_num = last_done.assembly_step.step_number if last_done else 0

        # Определяем следующий шаг
        next_step = steps.filter(step_number__gt=last_step_num).first()
        if not next_step:
            return JsonResponse({'status': 'complete'})

        TaskLog.objects.create(
            truck_run=truck_run, assembly_step=next_step, 
            operator=worker, start_time=timezone.now()
        )
        return JsonResponse({'status': 'started', 'step_number': next_step.step_number})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def station_data_api(request, station_slug):
    """ Возвращает все данные для UI """
    station = get_object_or_404(WorkStation, slug=station_slug)
    
    # Рабочие этой станции
    workers = Worker.objects.filter(assigned_station=station).values('name', 'badge_id', 'role')
    
    # Очередь тракторов (is_active=False)
    available_trucks = TruckRun.objects.filter(workstation=station, is_active=False).select_related("product")
    available_data = [{
        "id": t.id, "vin": t.truck_serial_number, 
        "model": t.product.name if t.product else "",
        "image": t.product.image.url if t.product and t.product.image else ""
    } for t in available_trucks]

    # Активный трактор (is_active=True)
    truck_run = TruckRun.objects.filter(current_station=station.id, is_active=True).last()
    
    tasks_data = []
    current_step_id = None
    
    # Шаги и логи
    steps = AssemblyStep.objects.filter(workstation=station).order_by('step_number')
    log_map = {}
    if truck_run:
        logs = TaskLog.objects.filter(truck_run=truck_run).select_related('assembly_step')
        log_map = {log.assembly_step.id: log for log in logs}

    for step in steps:
        log = log_map.get(step.id)
        status, color = 'PENDING', 'PENDING'
        if log:
            if log.end_time: status, color = 'DONE', log.status_color or 'GREEN'
            else: status, color, current_step_id = 'IN_PROGRESS', 'BLUE', step.id

        tasks_data.append({
            'id': step.id, 'step_number': step.step_number, 
            'description': step.description, 'status': status, 'color': color
        })

    return JsonResponse({
        'status': 'active',
        'available_trucks': available_data,
        'truck_serial_number': truck_run.truck_serial_number if truck_run else "",
        'truck_image_url': truck_run.product.image.url if truck_run and truck_run.product and truck_run.product.image else "",
        'workers': list(workers),
        'tasks': tasks_data,
        'current_step_id': current_step_id
    })

@csrf_exempt
def take_over_task_api(request, station_slug):
    """ Brigadier intervention logic """
    data = json.loads(request.body)
    new_worker_badge = data.get('operator_id')
    station = get_object_or_404(WorkStation, slug=station_slug)
    worker = Worker.objects.filter(badge_id=new_worker_badge).first()
    
    active_task = TaskLog.objects.filter(truck_run__workstation=station, truck_run__is_active=True, end_time__isnull=True).first()
    if active_task:
        active_task.operator = worker
        active_task.was_intervened = True
        active_task.save()
        return JsonResponse({'status': 'switched', 'new_operator': worker.badge_id})
    return JsonResponse({'status': 'ignored'})

@csrf_exempt
def reset_truck_api(request, station_slug):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)
    pin = data.get('pin')
    station = get_object_or_404(WorkStation, slug=station_slug)
    
    # Security Check using the station object
    if pin != station.reset_pin:
        return JsonResponse({'success': False, 'message': 'Invalid PIN'})
    
    # FIX: Use the 'station' object directly in the filter
    old_run = TruckRun.objects.filter(workstation=station, is_active=True).last()
    
    if old_run:
        old_run.is_active = False
        old_run.save()
        
        # Start a fresh run for the same product
        TruckRun.objects.create(
            workstation=station, 
            product=old_run.product, 
            is_active=True
        )
        
    return JsonResponse({'success': True})

@csrf_exempt
def select_task_api(request, station_slug):
    data = json.loads(request.body)
    worker = Worker.objects.filter(badge_id=data.get('worker_id')).first()
    step = get_object_or_404(AssemblyStep, id=data.get('step_id'))
    truck_run = TruckRun.objects.filter(workstation__slug=station_slug, is_active=True).last()

    TaskLog.objects.filter(truck_run=truck_run, end_time__isnull=True).update(end_time=timezone.now())
    TaskLog.objects.create(truck_run=truck_run, assembly_step=step, operator=worker, start_time=timezone.now())
    return JsonResponse({'success': True})

def dashboard_api(request):
    """Returns data for all stations for the production dashboard"""
    stations = WorkStation.objects.filter(is_active=True).order_by('name')[:12]
    stations_data = []

    for station in stations:
        truck_run = TruckRun.objects.select_related("product").filter(
            workstation=station,
            is_active=True
        ).last()
        if not truck_run:
            stations_data.append({
                'station_name': station.name,
                'station_slug': station.slug,
                'status': 'empty',
                'status_color': 'GRAY',
                'truck_serial_number': '',
                'truck_image_url': '',
                'truck_name': '',
                'current_worker': '',
                'progress_percent': 0,
            })
            continue

        steps = AssemblyStep.objects.filter(
            workstation=station,
            product=truck_run.product
        ).order_by('step_number')

        logs = TaskLog.objects.filter(truck_run=truck_run).select_related('operator','assembly_step')
        log_map = {log.assembly_step.id: log for log in logs}

        progress_percent = 0
        current_task_color = 'BLUE'
        current_worker = None

        for step in steps:
            log = log_map.get(step.id)

            if log and not log.end_time:

                if log.operator:
                    current_worker = log.operator.name

                std_sec = step.standard_duration_seconds or 180

                start_utc = log.start_time if log.start_time.tzinfo else timezone.make_aware(log.start_time)
                start_utc = start_utc.astimezone(dt_timezone.utc)

                now_utc = datetime.now(dt_timezone.utc)

                elapsed_sec = (now_utc - start_utc).total_seconds()

                progress_percent = min(100.0, (elapsed_sec / std_sec) * 100)

                if elapsed_sec < std_sec * 0.5:
                    current_task_color = 'GREEN'
                elif elapsed_sec < std_sec * 0.8:
                    current_task_color = 'YELLOW'
                else:
                    current_task_color = 'RED'

                break

        status_color = current_task_color if progress_percent > 0 else 'BLUE'

        stations_data.append({
            'station_name': station.name,
            'station_slug': station.slug,
            'status': 'active',
            'status_color': status_color,
            'truck_serial_number': truck_run.truck_serial_number or '',
            'truck_image_url': truck_run.product.image.url if truck_run.product.image else '',
            'truck_name': truck_run.product.name,
            'current_worker': current_worker or '',
            'progress_percent': round(progress_percent,1),
            'current_task_color': current_task_color,
        })

    return JsonResponse({'stations': stations_data})

def worker_by_badge(request, badge):

    try:
        worker = Worker.objects.get(badge_id=badge)

        return JsonResponse({
            "name": worker.name,
            "badge": worker.badge_id,
            "role": worker.role
        })

    except Worker.DoesNotExist:

        return JsonResponse({"error":"not found"})
    


@csrf_exempt
def create_reorder(request):

    try:

        data = json.loads(request.body)
        part_code = data.get("part")

        print("REORDER:", part_code)

        part = Part.objects.filter(code=part_code).first()

        if not part:
            return JsonResponse({"status": "part_not_found"})

        order = PurchaseOrder.objects.create(
            part=part,
            quantity=part.reorder_quantity
        )

        return JsonResponse({
            "status": "created",
            "order_id": order.id
        })

    except Exception as e:

        print("REORDER ERROR:", e)

        return JsonResponse({
            "status": "error",
            "message": str(e)
        })
    





@csrf_exempt
def start_truck_api(request, station_slug):
    """ Кнопка ACCEPT: Активирует трактор и привязывает его к станции """
    data = json.loads(request.body)
    truck_id = data.get('truck_id')
    station = get_object_or_404(WorkStation, slug=station_slug)
    
    # Сбрасываем старые активные тракторы на этой станции
    TruckRun.objects.filter(current_station=station.id, is_active=True).update(is_active=False)
    
    # Активируем новый
    truck = get_object_or_404(TruckRun, id=truck_id)
    truck.is_active = True
    truck.current_station = station.id  # ОЧЕНЬ ВАЖНО: записываем ID станции
    truck.save()
    
    return JsonResponse({'status': 'success'})









