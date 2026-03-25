import pandas as pd
import re
from django.core.management.base import BaseCommand
from core.models import Part, Inventory

class Command(BaseCommand):
    help = 'Импорт всех деталей из ВСЕХ вкладок Excel файла (с распределением по Станциям)'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Путь к файлу Excel')

    def handle(self, *args, **kwargs):
        file_path = kwargs['file_path']
        
        self.stdout.write(self.style.WARNING(f"Открываем файл: {file_path}... ищем детали на ВСЕХ вкладках!"))

        try:
            # Читаем сразу все вкладки
            all_sheets = pd.read_excel(file_path, sheet_name=None, header=None, engine='openpyxl')
            
            added_count = 0
            skipped_count = 0

            for sheet_name, df_raw in all_sheets.items():
                self.stdout.write(self.style.WARNING(f"➡️ Сканируем вкладку: {sheet_name}"))
                
                # --- ИЩЕМ НОМЕР СТАНЦИИ ИЗ НАЗВАНИЯ ВКЛАДКИ ---
                # Если вкладка называется "2 пост", скрипт вытащит цифру 2
                match = re.search(r'\d+', sheet_name)
                station_num = match.group() if match else "1"
                location_name = f"Станция {station_num}"
                
                header_idx = None
                for i, row in df_raw.iterrows():
                    row_str = [str(cell).strip().lower() for cell in row.values]
                    if 'обозначение' in row_str and 'наименование' in row_str:
                        header_idx = i
                        break
                
                if header_idx is None:
                    self.stdout.write(self.style.WARNING(f"⚠️ На вкладке '{sheet_name}' нет нужных колонок. Пропускаем."))
                    continue
                    
                df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx, engine='openpyxl')
                
                for index, row in df.iterrows():
                    # === ИСПРАВЛЕНИЕ ОШИБКИ: Обрезаем код до 50 символов, чтобы база не падала ===
                    code = str(row.get('Обозначение', '')).strip()[:50]
                    name = str(row.get('Наименование', '')).strip()[:200]

                    if not code or code.lower() == 'nan' or not name or name.lower() == 'nan':
                        continue

                    # Создаем деталь
                    part, created = Part.objects.get_or_create(
                        code=code,
                        defaults={'name': name}
                    )

                    # === ИСПРАВЛЕНИЕ ЛОКАЦИИ: Привязываем Инвентарь к конкретной станции ===
                    _, inv_created = Inventory.objects.get_or_create(
                        part=part,
                        location=location_name,
                        defaults={'quantity': 0}
                    )

                    if inv_created:
                        added_count += 1
                    else:
                        skipped_count += 1

            self.stdout.write(self.style.SUCCESS(f"\n✅ ГОТОВО! Новых записей на складе: {added_count}. Уже было: {skipped_count}."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Ошибка при чтении файла: {str(e)}"))