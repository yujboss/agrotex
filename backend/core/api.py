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
import math
from .models import WorkStation, Worker, TruckRun, TaskLog, AssemblyStep
from .models import StepPart, Inventory, PartConsumption
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from core.models import Part, Order
from core.models import PurchaseOrder
import logging 
import os      
from django.conf import settings
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from core.models import TruckRun, Worker, DefectLog, TaskLog
# ==========================================
# НАСТРОЙКА ЛОГГЕРА ДЛЯ FACE ID (AUDIT LOGGING)
# ==========================================
face_logger = logging.getLogger('face_audit')
face_logger.setLevel(logging.INFO)

# Файл будет сохраняться в корне проекта (там же, где manage.py)
log_file_path = os.path.join(settings.BASE_DIR, 'face_audit.log') if hasattr(settings, 'BASE_DIR') else 'face_audit.log'

if not face_logger.handlers:
    fh = logging.FileHandler(log_file_path, encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh.setFormatter(formatter)
    face_logger.addHandler(fh)
# ==========================================

@csrf_exempt
def next_task_api(request, station_slug):
    """ Handles Space Bar: Closes current task, starts the next one """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        worker_badge = data.get('operator_id')
        incoming_face = data.get('face_descriptor')
        
        station = get_object_or_404(WorkStation, slug=station_slug)
        
        # === ИСПРАВЛЕНИЕ: ПОИСК ТОЛЬКО ПО ТЕКУЩЕЙ СТАНЦИИ ===
        worker = Worker.objects.filter(badge_id=worker_badge, assigned_station=station).first()

        if not worker:
            face_logger.warning(f"Станция: {station.name} | Бейдж: {worker_badge} | Результат: FAILURE (Рабочий не найден или с чужой станции)")
            return JsonResponse({'error': 'Рабочий не найден или не прикреплен к этой станции! Проверка отменена.'})

        # ==========================================================
        # === ШАГ 5: ПРОВЕРКА ЛИЦА (FACE VERIFICATION) =============
        # ==========================================================
        if not worker.face_descriptor:
            face_logger.warning(f"Станция: {station.name} | Рабочий: {worker.name} | Результат: FAILURE (Нет лица в базе)")
            return JsonResponse({'error': f'У рабочего {worker.name} нет слепка лица в базе! Зайдите в Админку и оцифруйте его.'})
            
        if not incoming_face:
            face_logger.warning(f"Станция: {station.name} | Рабочий: {worker.name} | Результат: FAILURE (Пустые данные с камеры)")
            return JsonResponse({'error': 'С камеры не пришли данные лица. Попробуйте еще раз.'})

        # Считаем Евклидово расстояние между лицом с камеры и лицом из базы
        if len(incoming_face) == len(worker.face_descriptor):
            sum_sq = sum((a - b) ** 2 for a, b in zip(incoming_face, worker.face_descriptor))
            distance = math.sqrt(sum_sq)
        else:
            distance = 1.0 # Если массивы разной длины - 100% ошибка

        # Порог (Threshold). Меньше 0.55 -> это тот же человек.
        if distance > 0.55:
            # Лицо не совпало! Записываем в лог и блокируем.
            face_logger.warning(f"Станция: {station.name} | Рабочий: {worker.name} | Сходство: {distance:.2f} | Результат: FAILURE (Лицо не совпало)")
            return JsonResponse({'error': f'ВНИМАНИЕ! Лицо не совпадает с бейджем ({worker.name}). Доступ запрещен!'})
        
        # ЕСЛИ ВСЁ ОК - ПИШЕМ УСПЕХ В ЛОГ
        face_logger.info(f"Станция: {station.name} | Рабочий: {worker.name} | Сходство: {distance:.2f} | Результат: SUCCESS")
        # ==========================================================


        # Ищем активный трактор именно по current_station
        truck_run = TruckRun.objects.filter(
            current_station=station.id,
            is_active=True
        ).last()

        if not truck_run:
            return JsonResponse({'status': 'no_truck'})

        if truck_run.status == 'REWORK':
            return JsonResponse({'error': '⛔ Трактор находится в доработке! Сборка заблокирована Мастером.'})
        # =========================================

        # Загружаем шаги для этой станции ИМЕННО ДЛЯ ЭТОГО ТРАКТОРА
        if truck_run.product:
            steps = AssemblyStep.objects.filter(workstation=station, product=truck_run.product).order_by('step_number')
        else:
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
                    
                    # --- TELEGRAM УВЕДОМЛЕНИЯ ---
                    status = inventory.stock_status()
                    if status in ["YELLOW", "RED"]:
                        time_str = timezone.now().astimezone().strftime("%d.%m %H:%M")
                        operator_name = worker.name if worker else "Unknown"
                        step_desc = active_task.assembly_step.description
                        
                        if status == "YELLOW":
                            msg = f"⚠ LOW STOCK\n\nPart: {inventory.part.code}\nStock: {inventory.quantity}\n\nStation: {station.name}\nStep: {step_desc}\nOperator: {operator_name}\nTime: {time_str}"
                        else:
                            msg = f"🚨 CRITICAL STOCK\n\nPart: {inventory.part.code}\nStock: {inventory.quantity}\n\nStation: {station.name}\nStep: {step_desc}\nOperator: {operator_name}\nTime: {time_str}\n\nCALL WAREHOUSE"
                        
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
            # Если активных задач нет, смотрим последнюю завершенную ИМЕННО НА ЭТОЙ СТАНЦИИ
            last_done = TaskLog.objects.filter(
                truck_run=truck_run, 
                assembly_step__workstation=station, 
                end_time__isnull=False
            ).order_by('end_time').last()
            last_step_num = last_done.assembly_step.step_number if last_done else 0

        # Определяем следующий шаг
        next_step = steps.filter(step_number__gt=last_step_num).first()
        
        if not next_step:
            # === ТРАКТОР ПРОШЕЛ ВСЕ ШАГИ НА ЭТОЙ СТАНЦИИ ===
            truck_run.is_active = False 
            
            # Ищем следующую станцию
            next_station = WorkStation.objects.filter(id__gt=station.id, is_active=True).order_by('id').first()
            
            if next_station:
                truck_run.workstation = next_station
                truck_run.current_station = next_station.id 
            else:
                truck_run.is_finished = True
                
            truck_run.save()
            return JsonResponse({'status': 'complete'})

        # === ПРОВЕРКА СКЛАДА ПЕРЕД НАЧАЛОМ СЛЕДУЮЩЕГО ШАГА ========
        missing_parts = []
        next_step_parts = StepPart.objects.filter(assembly_step=next_step)
        
        for sp in next_step_parts:
            inventory = Inventory.objects.filter(part_id=sp.part_id).first()
            current_qty = inventory.quantity if inventory else 0
            if current_qty < sp.quantity:
                missing_parts.append(f"{sp.part.code} (Надо: {sp.quantity}, Есть: {current_qty})")
                
        if missing_parts:
            time_str = timezone.now().astimezone().strftime("%d.%m %H:%M")
            operator_name = worker.name if worker else "Unknown"
            missing_str = "\n".join(missing_parts)
            
            msg = f"⛔ PRODUCTION STOPPED!\n\nCan't start next step.\nStation: {station.name}\nStep: {next_step.description}\nOperator: {operator_name}\nTime: {time_str}\n\nMissing parts:\n{missing_str}\n\nFILL WAREHOUSE FIRST!"
            send_telegram_message(msg)
            
            return JsonResponse({
                'status': 'error',
                'message': f"Деталей нет! Не хватает: {', '.join(missing_parts)}.\n\nЗаполните склад!"
            })

        if not active_task:
            # СТАРТУЕМ НОВУЮ ЗАДАЧУ
            TaskLog.objects.create(
                truck_run=truck_run, assembly_step=next_step, 
                operator=worker, start_time=timezone.now()
            )
            return JsonResponse({'status': 'started', 'step_number': next_step.step_number})
            
        timer_standard = next_step.standard_duration_seconds or 180
        
        return JsonResponse({
            'status': 'step_ready', 
            'message': 'Шаг завершен. Выберите оператора для следующего этапа.',
            'next_step_number': next_step.step_number,
            'next_step_description': next_step.description,
            'current_task_start_time': None,
            'current_task_elapsed_seconds': 0,
            'current_task_standard_seconds': timer_standard
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def station_data_api(request, station_slug):
    """ Возвращает все данные для UI """
    station = get_object_or_404(WorkStation, slug=station_slug)
    
    # Берем всех рабочих станции, КРОМЕ ТЕХ, кого сейчас заменяют (substituted_by__isnull=True)
    workers = Worker.objects.filter(
        assigned_station=station, 
        substituted_by__isnull=True 
    ).values('name', 'badge_id', 'role', 'is_substitute') 
    # Очередь тракторов (is_active=False)
    available_trucks = TruckRun.objects.filter(workstation=station, is_active=False).select_related("product")
    available_data = [{
        "id": t.id, "vin": t.truck_serial_number, 
        "model": t.product.name if t.product else "",
        "image": t.product.image.url if t.product and t.product.image else ""
    } for t in available_trucks]

    # Активный трактор (is_active=True)
    truck_run = TruckRun.objects.filter(workstation=station, is_active=True).last()  
    tasks_data = []
    current_step_id = None
    


    # ВАЖНО: Создаем переменные для таймера ДО цикла
    timer_start_time = None
    timer_elapsed = None
    timer_standard = None
    
    # Шаги и логи
    steps = AssemblyStep.objects.filter(workstation=station).order_by('step_number')
    log_map = {}
    if truck_run:
        logs = TaskLog.objects.filter(truck_run=truck_run).select_related('assembly_step')
        log_map = {log.assembly_step.id: log for log in logs}

    tasks_data = []
    current_step_id = None
    current_operator_badge = None  # <--- НОВОЕ: Переменная для бейджа текущего рабочего
    
    # ВАЖНО: Создаем переменные для таймера ДО цикла
    timer_start_time = None
    timer_elapsed = None
    timer_standard = None
    
    # Шаги и логи
    # === НОВАЯ ЛОГИКА: Грузим шаги ТОЛЬКО для текущего трактора ===
    if truck_run and truck_run.product:
        steps = AssemblyStep.objects.filter(workstation=station, product=truck_run.product).order_by('step_number')
    else:
        # Если трактора на станции нет, то и шаги не показываем
        steps = AssemblyStep.objects.none()

    for step in steps:
        log = log_map.get(step.id)
        status = 'PENDING'
        color = 'PENDING'
        
        # НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ СПИСКА:
        operator_name = "-"
        time_spent_sec = 0

        if log:
            if log.operator:
                # Берем имя оператора (можно сделать обрезку до фамилии, если нужно)
                operator_name = log.operator.name

            if log.end_time:
                status = 'DONE'
                color = log.status_color or 'GREEN'
                # Считаем потраченное время для завершенных задач
                time_spent_sec = int((log.end_time - log.start_time).total_seconds())
            else:
                status = 'IN_PROGRESS'
                color = 'BLUE'
                current_step_id = step.id
                if log.operator:
                    current_operator_badge = log.operator.badge_id

                # Считаем время в реальном времени для текущей задачи
                start_utc = log.start_time if log.start_time.tzinfo else timezone.make_aware(log.start_time)
                start_utc = start_utc.astimezone(dt_timezone.utc)
                now_utc = datetime.now(dt_timezone.utc)
                time_spent_sec = int((now_utc - start_utc).total_seconds())

        # Норматив
        std_sec = int(step.standard_duration_seconds or 180)

        # Если это текущая задача, прокидываем переменные для большого таймера
        if status == 'IN_PROGRESS':
            timer_start_time = log.start_time.isoformat()
            timer_standard = std_sec
            timer_elapsed = time_spent_sec

        parts_info = []
        for sp in step.required_parts.select_related('part').all():
            parts_info.append({
                "code": sp.part.code,
                "name": sp.part.name,
                "qty": sp.quantity,
                "package": sp.package_number if sp.package_number else ""
            })

        tasks_data.append({
            'id': step.id,
            'step_number': step.step_number,
            'description': step.description,
            'category_name': step.category.name if step.category else "ОБЩИЕ РАБОТЫ", # Категория из БД
            'operator_name': operator_name,
            'time_spent_sec': time_spent_sec,
            'standard_sec': std_sec,
            'heading': step.heading if step.heading else f"Шаг {step.step_number}",
            'status': status,
            'color': color,
            "tooling": step.tooling,
            "parts": parts_info
        })

    return JsonResponse({
        'status': 'active',
        'available_trucks': available_data,
        'truck_serial_number': truck_run.truck_serial_number if truck_run else "",
        'truck_image_url': truck_run.product.image.url if truck_run and truck_run.product and truck_run.product.image else "",
        'workers': list(workers),
        'tasks': tasks_data,
        'current_step_id': current_step_id,
        'current_truck_id': truck_run.id if truck_run else None,
        # ТЕПЕРЬ ПЕРЕДАЕМ НАСТОЯЩИЕ ЗНАЧЕНИЯ, А НЕ None
        'current_task_start_time': timer_start_time,
        # <--- НОВОЕ: Отправляем бейдж рабочего на фронтенд
        'current_operator_badge': current_operator_badge,
        # --- НОВАЯ СТРОЧКА: Отправляем название модели ---
        'truck_model_name': truck_run.product.name if truck_run and truck_run.product else "",
        'current_task_elapsed_seconds': timer_elapsed,
        'current_task_standard_seconds': timer_standard,
        'truck_status': truck_run.status if truck_run else 'IN_PROGRESS'
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
            current_station=station.id,
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
                'current_task_name': '',
            })
            continue

        # Загружаем шаги именно для этой модели трактора
        if truck_run.product:
            steps = list(AssemblyStep.objects.filter(workstation=station, product=truck_run.product).order_by('step_number'))
        else:
            steps = list(AssemblyStep.objects.filter(workstation=station).order_by('step_number'))

        logs = TaskLog.objects.filter(truck_run=truck_run).select_related('operator','assembly_step')
        log_map = {log.assembly_step.id: log for log in logs}

        total_steps = len(steps)
        completed_steps = 0
        
        current_task_color = 'BLUE'
        current_worker = None
        current_task_name = 'Ожидание...'
        active_step_found = False

        for step in steps:
            log = log_map.get(step.id)

            if log:
                if log.end_time:
                    completed_steps += 1  # Считаем для ОБЩЕГО прогресса (ширина полоски)
                else:
                    # НАШЛИ АКТИВНУЮ ЗАДАЧУ (Она управляет ЦВЕТОМ карточки)
                    active_step_found = True
                    if log.operator:
                        current_worker = log.operator.name

                    std_sec = step.standard_duration_seconds or 180
                    start_utc = log.start_time if log.start_time.tzinfo else timezone.make_aware(log.start_time)
                    start_utc = start_utc.astimezone(dt_timezone.utc)
                    now_utc = datetime.now(dt_timezone.utc)
                    elapsed_sec = (now_utc - start_utc).total_seconds()

                    # Цвет зависит от того, успеваем ли мы по нормативу ТЕКУЩЕЙ задачи!
                    task_percent = min(100.0, (elapsed_sec / std_sec) * 100)
                    if task_percent < 50:
                        current_task_color = 'GREEN'
                    elif task_percent < 80:
                        current_task_color = 'YELLOW'
                    else:
                        current_task_color = 'RED'

                    current_task_name = f"STEP {step.step_number}: {step.description}"
        
        # Если все завершили или еще не начали
        if not active_step_found:
            if total_steps > 0 and completed_steps == total_steps:
                current_task_color = 'GREEN'
                current_task_name = 'Все задачи завершены'
            else:
                current_task_color = 'BLUE'
                # Ищем первый невыполненный шаг
                next_step = next((s for s in steps if s.id not in [l.assembly_step.id for l in logs if l.end_time]), None)
                if next_step:
                    current_task_name = f"ОЖИДАНИЕ: STEP {next_step.step_number}"

        # --- СЧИТАЕМ ОБЩИЙ ПРОГРЕСС ТРАКТОРА (ТЕ САМЫЕ 17%) ---
        overall_progress = (completed_steps / total_steps * 100) if total_steps > 0 else 0

        stations_data.append({
            'station_name': station.name,
            'station_slug': station.slug,
            'status': 'active',
            'status_color': current_task_color, # ЦВЕТ берем от таймера шага
            'truck_serial_number': truck_run.truck_serial_number or '',
            'truck_image_url': truck_run.product.image.url if truck_run.product and truck_run.product.image else '',
            'truck_name': truck_run.product.name if truck_run.product else '',
            'current_worker': current_worker or '',
            'progress_percent': round(overall_progress, 1), # ШИРИНУ БАРА берем от общего прогресса (17%)
            'current_task_color': current_task_color, 
            'current_task_name': current_task_name, 
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
        
        # Получаем количество, которое ввел кладовщик
        try:
            quantity_to_add = int(data.get("quantity", 0))
        except (ValueError, TypeError):
            quantity_to_add = 0

        print(f"REORDER: {part_code}, QTY: {quantity_to_add}")

        part = Part.objects.filter(code=part_code).first()

        if not part:
            return JsonResponse({"status": "error", "message": "Part not found"})

        if quantity_to_add <= 0:
            return JsonResponse({"status": "error", "message": "Введите количество больше 0"})

        # 1. Создаем Purchase Order (история заказов для админки)
        order = PurchaseOrder.objects.create(
            part=part,
            quantity=quantity_to_add,
            status="COMPLETED" # Можем сразу ставить статус COMPLETED, раз пополняем склад
        )

        # 2. СРАЗУ ПОПОЛНЯЕМ СКЛАД (Inventory), чтобы конвейер мог работать
        inventory = Inventory.objects.filter(part=part).first()
        if inventory:
            inventory.quantity += quantity_to_add
            inventory.save()

        return JsonResponse({
            "status": "created",
            "order_id": order.id,
            "new_quantity": inventory.quantity if inventory else quantity_to_add
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





@csrf_exempt
def report_defect_api(request, slug):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            truck_id = data.get('truck_id')
            worker_badge = data.get('worker_id')
            step_id = data.get('step_id')  # <--- ЛОВИМ ВЫБРАННЫЙ ШАГ ОТ JS
            category = data.get('category')
            description = data.get('description')
            is_critical = data.get('is_critical')

            truck_run = TruckRun.objects.get(id=truck_id)
            worker = Worker.objects.get(badge_id=worker_badge)
            step = AssemblyStep.objects.get(id=step_id) # <--- БЕРЕМ КОНКРЕТНЫЙ ШАГ

            # Сохраняем дефект
            DefectLog.objects.create(
                truck_run=truck_run,
                assembly_step=step, 
                worker=worker,
                category=category,
                description=description,
                is_critical=is_critical
            )

            # Логика остановки конвейера
            if is_critical:
                truck_run.status = 'REWORK'
                truck_run.save()
                return JsonResponse({"status": "critical"})

            return JsonResponse({"status": "ok"})
            
        except Exception as e:
            return JsonResponse({"status": "error", "error": str(e)}, status=400)


