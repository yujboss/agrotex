import pandas as pd
from django.core.management.base import BaseCommand
from core.models import Part, Inventory
import math

class Command(BaseCommand):
    help = 'Импорт деталей (Обозначение и Наименование) из Excel файла с предварительной очисткой'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Путь к файлу Excel')

    def handle(self, *args, **kwargs):
        file_path = kwargs['file_path']
        
        self.stdout.write(self.style.WARNING(f"Открываем файл: {file_path}..."))

        try:
            # Сначала читаем файл без заголовков, чтобы найти нужную строку
            df_raw = pd.read_excel(file_path, header=None, engine='openpyxl')
            
            header_idx = None
            # Ищем строку, где есть слова 'Обозначение' и 'Наименование'
            for i, row in df_raw.iterrows():
                row_str = [str(cell).strip().lower() for cell in row.values]
                if 'обозначение' in row_str and 'наименование' in row_str:
                    header_idx = i
                    break
            
            if header_idx is None:
                self.stdout.write(self.style.ERROR("❌ Не удалось найти колонки 'Обозначение' и 'Наименование' в файле!"))
                return
                
            self.stdout.write(self.style.SUCCESS(f"Заголовки найдены на строке {header_idx + 1}."))

            # ========================================================
            # БЛОК ОЧИСТКИ БАЗЫ ДАННЫХ ПЕРЕД ИМПОРТОМ
            # ========================================================
            self.stdout.write(self.style.WARNING("Удаляем старые записи из базы..."))
            Inventory.objects.all().delete()  # Сначала удаляем инвентарь
            Part.objects.all().delete()       # Затем удаляем сами детали
            self.stdout.write(self.style.SUCCESS("✅ Старая база успешно очищена! Начинаем импорт..."))
            # ========================================================

            # Теперь читаем файл нормально, начиная с найденной строки
            df = pd.read_excel(file_path, header=header_idx, engine='openpyxl')
            
            added_count = 0
            skipped_count = 0

            for index, row in df.iterrows():
                code = str(row.get('Обозначение', '')).strip()
                name = str(row.get('Наименование', '')).strip()

                # Пропускаем пустые строки или строки-заголовки, где нет Обозначения
                if not code or code.lower() == 'nan':
                    continue
                if not name or name.lower() == 'nan':
                    continue

                # Создаем деталь (если такой code уже есть, get_or_create просто вернет её)
                part, created = Part.objects.get_or_create(
                    code=code,
                    defaults={'name': name}
                )

                if created:
                    # Сразу создаем запись на складе с нулевым остатком
                    Inventory.objects.get_or_create(
                        part=part,
                        defaults={
                            'quantity': 0,
                            'location': "Main Warehouse"
                        }
                    )
                    self.stdout.write(self.style.SUCCESS(f"➕ Добавлено: {code} - {name}"))
                    added_count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"⏩ Пропущено (уже есть в базе): {code} - {name}"))
                    skipped_count += 1

            self.stdout.write(self.style.SUCCESS(f"\n✅ ГОТОВО! Добавлено новых деталей: {added_count}. Пропущено: {skipped_count}."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Ошибка при чтении файла: {str(e)}"))