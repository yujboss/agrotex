import pandas as pd
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from core.models import Part, WorkStation, ProductVariant, AssemblyStep, StepPart
import random

class Command(BaseCommand):
    help = 'Импорт техкарт с поддержкой вкладок (листов) Excel и сбором всей оснастки'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Путь к файлу')
        parser.add_argument('--post', type=str, default='Станция 1', help='Название станции')
        parser.add_argument('--product', type=str, default='Belarus 80.1', help='Название продукта')
        parser.add_argument('--sheet', type=str, default='0', help='Название вкладки в Excel')

    def handle(self, *args, **kwargs):
        file_path = kwargs['file_path']
        post_name = kwargs['post']
        product_name = kwargs['product']
        sheet_name = kwargs['sheet']

        if sheet_name.isdigit():
            sheet_name = int(sheet_name)

        self.stdout.write(self.style.WARNING(f"Начинаем импорт: {file_path} | Станция: {post_name} | Лист: {sheet_name}"))

        product_code = slugify(product_name) or f"prod-{random.randint(1000, 9999)}"
        product, _ = ProductVariant.objects.get_or_create(name=product_name, defaults={'code': product_code})

        clean_post_name = post_name.strip()
        workstation = WorkStation.objects.filter(name__iexact=clean_post_name).first()
        if not workstation:
            workstation = WorkStation.objects.create(
                name=clean_post_name, 
                slug=slugify(clean_post_name) or f"st-{random.randint(100, 999)}", 
                ip_address=f"10.0.0.{WorkStation.objects.count() + 1}"
            )

        AssemblyStep.objects.filter(workstation=workstation, product=product).delete()
        self.stdout.write(self.style.SUCCESS("✅ Старые шаги удалены. Начинаем загрузку новых..."))

        try:
            if file_path.endswith('.csv'):
                try: df_raw = pd.read_csv(file_path, sep=';', encoding='utf-8-sig', header=None)
                except: df_raw = pd.read_csv(file_path, sep=';', encoding='cp1251', header=None)
            else:
                df_raw = pd.read_excel(file_path, header=None, engine='openpyxl', sheet_name=sheet_name)

            header_idx = 0
            for i, row in df_raw.iterrows():
                row_str = [str(cell).strip().lower() for cell in row.values]
                if 'обозначение' in row_str:
                    header_idx = i
                    break
            
            if file_path.endswith('.csv'):
                try: df = pd.read_csv(file_path, sep=';', encoding='utf-8-sig', header=header_idx)
                except: df = pd.read_csv(file_path, sep=';', encoding='cp1251', header=header_idx)
            else:
                df = pd.read_excel(file_path, header=header_idx, engine='openpyxl', sheet_name=sheet_name)

            df.columns = [str(c).strip().lower() for c in df.columns]

            col_no = next((c for c in df.columns if '№' in c and 'пакет' not in c), df.columns[0])
            col_code = next((c for c in df.columns if 'обозначение' in c), None)
            col_qty = next((c for c in df.columns if 'кол' in c), None)
            col_desc = next((c for c in df.columns if 'описание' in c), None)
            col_tooling = next((c for c in df.columns if 'оснастка' in c), None)
            col_torque = next((c for c in df.columns if 'момент' in c), None)
            col_time = next((c for c in df.columns if 'время' in c), None)
            col_package = next((c for c in df.columns if 'пакет' in c), None)

            grouped_steps = []
            current_heading = "Основная сборка"
            current_step = None

            for index, row in df.iterrows():
                no_val = str(row.get(col_no, '')).strip()
                code_val = str(row.get(col_code, '')).strip()
                desc_val = str(row.get(col_desc, '')).strip()
                if desc_val.lower() == 'nan': desc_val = ''

                has_letters = any(c.isalpha() for c in no_val)
                if no_val and no_val.lower() != 'nan' and has_letters and (code_val.lower() == 'nan' or not code_val):
                    current_heading = no_val
                    continue 

                if (not no_val or no_val.lower() == 'nan') and (not code_val or code_val.lower() == 'nan') and not desc_val:
                    continue

                # --- 1. ЕСЛИ ЕСТЬ ОПИСАНИЕ - СОЗДАЕМ НОВЫЙ ШАГ ---
                if desc_val:
                    t_val = str(row.get(col_time, '0')).strip()
                    try: time_min = float(t_val)
                    except: time_min = 5.0 

                    current_step = {
                        'heading': current_heading,
                        'description': desc_val,
                        'time_min': time_min, # Оставляем парсинг на всякий случай, но использовать не будем
                        'tooling': '', 
                        'torque': '',
                        'parts': []
                    }
                    grouped_steps.append(current_step)

                # --- 2. УМНЫЙ СБОР ОСНАСТКИ СО ВСЕХ СТРОК ---
                if current_step:
                    tool_val = str(row.get(col_tooling, '')).strip()
                    if tool_val and tool_val.lower() != 'nan':
                        if not current_step['tooling']:
                            current_step['tooling'] = tool_val
                        elif tool_val not in current_step['tooling']: # Добавляем только уникальные
                            current_step['tooling'] += f" / {tool_val}"

                    torq_val = str(row.get(col_torque, '')).strip()
                    if torq_val and torq_val.lower() != 'nan':
                        if not current_step['torque']:
                            current_step['torque'] = torq_val
                        elif torq_val not in current_step['torque']:
                            current_step['torque'] += f" / {torq_val}"

                # --- 3. СОБИРАЕМ ДЕТАЛИ ---
                if code_val and code_val.lower() != 'nan':
                    # Защита от кривых строк: если детали есть, а описания шага не было
                    if not current_step:
                        current_step = {
                            'heading': current_heading,
                            'description': 'Сборка',
                            'time_min': 5.0,
                            'tooling': '',
                            'torque': '',
                            'parts': []
                        }
                        grouped_steps.append(current_step)

                    qty = 1
                    if col_qty:
                        q_val = str(row.get(col_qty, '1')).strip()
                        try: qty = int(float(q_val))
                        except: qty = 1
                    
                    pkg_val = ''
                    if col_package:
                        pkg_val = str(row.get(col_package, '')).strip()
                        if pkg_val.lower() == 'nan': pkg_val = ''
                    
                    current_step['parts'].append({
                        'code': code_val, 
                        'qty': qty, 
                        'package': pkg_val
                    })

            # =========================================================================
            # НОВАЯ ЛОГИКА: Подсчитываем количество шагов внутри каждого заголовка
            # =========================================================================
            heading_step_counts = {}
            for step_data in grouped_steps:
                h = step_data['heading']
                heading_step_counts[h] = heading_step_counts.get(h, 0) + 1

            global_step_counter = 0
            parts_linked = 0

            # Записываем всё в БД
            for step_data in grouped_steps:
                global_step_counter += 1
                
                # Получаем сколько всего шагов в текущем заголовке
                steps_in_heading = heading_step_counts[step_data['heading']]
                
                # Делим 60 минут на количество шагов в заголовке
                # Например, если 3 шага: 60 / 3 = 20.0 минут. Умножаем на 60 сек = 1200 сек.
                calculated_time_min = 60.0 / steps_in_heading
                time_sec = int(calculated_time_min * 60)
                
                # Если собрали и момент, и инструмент, объединяем их красиво для вывода на экран
                final_tooling = step_data['tooling']
                if step_data['torque']:
                    if final_tooling: final_tooling += f" (Момент: {step_data['torque']})"
                    else: final_tooling = f"Момент: {step_data['torque']}"

                db_step = AssemblyStep.objects.create(
                    workstation=workstation,
                    product=product,
                    step_number=global_step_counter,
                    heading=step_data['heading'],
                    description=step_data['description'],
                    standard_duration_seconds=time_sec, # <-- Используем наше новое посчитанное время
                    tooling=final_tooling, 
                    torque=step_data['torque']
                )

                desc_preview = (db_step.description[:40] + '...') if len(db_step.description) > 40 else db_step.description
                self.stdout.write(self.style.SUCCESS(f"\n🛠️ Шаг {global_step_counter} [{db_step.heading}]: {desc_preview} ({time_sec} сек)"))
                if final_tooling:
                    self.stdout.write(self.style.WARNING(f"  🔧 Инструмент: {final_tooling}"))

                for p_data in step_data['parts']:
                    code = p_data['code']
                    try:
                        part = Part.objects.get(code=code)
                        StepPart.objects.create(
                            assembly_step=db_step, 
                            part=part, 
                            quantity=p_data['qty'],
                            package_number=p_data['package']
                        )
                        parts_linked += 1
                    except Part.DoesNotExist:
                        self.stdout.write(self.style.ERROR(f"  ❌ Деталь {code} не найдена в базе!"))

            self.stdout.write(self.style.SUCCESS(f"\n✅ ГОТОВО! Создано блоков (заданий): {global_step_counter}. Привязано деталей: {parts_linked}."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Ошибка: {str(e)}"))