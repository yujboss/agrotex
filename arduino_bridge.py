import serial
import requests
import time
import argparse

# ==========================================
# ⚙️ НАСТРОЙКИ ПО УМОЛЧАНИЮ
# ==========================================
BAUD_RATE = 9600

def connect_arduino(port):
    """Бесконечная попытка подключиться к Ардуино (защита от скачков)"""
    while True:
        try:
            ser = serial.Serial(port, BAUD_RATE, timeout=1)
            time.sleep(2) # Ардуино нужно пару секунд на перезагрузку после подключения
            print(f"✅ Arduino успешно подключена на порту {port}!")
            return ser
        except Exception:
            print(f"🔌 Жду Arduino на порту {port}... (проверь кабель)")
            time.sleep(3)

def main():
    # 1. Настраиваем чтение команд из батника или терминала
    parser = argparse.ArgumentParser(description="Мост между Django и светофором Arduino")
    parser.add_argument("station", nargs='?', default=None, help="Название станции (например: station3)")
    parser.add_argument("-p", "--port", default="COM4", help="COM-порт (по умолчанию COM4)")
    args = parser.parse_args()

    # 2. Если станция не указана при запуске — вежливо спрашиваем
    station_slug = args.station
    if not station_slug:
        print("\n=================================================")
        station_slug = input("👉 Введи станцию (например 1,2,3): ").strip()
        print("=================================================\n")

    serial_port = args.port
    api_url = f'http://agromax.uz/api/station/{station_slug}/status/'

    print(f"🔄 Запуск моста для станции «{station_slug}»...")
    
    # 3. Подключаемся к железу
    ser = connect_arduino(serial_port)
    
    # Переменные для отслеживания состояния
    last_color = None
    defect_blink_state = False # Горит сейчас красный или выключен (для мигания)
    defect_timer = 0           # Таймер для отсчета 5 секунд

    # 4. Главный бесконечный цикл программы
    while True:
        try:
            # Стучимся в Django API
            response = requests.get(api_url, timeout=2)
            
            if response.status_code == 200:
                data = response.json()
                current_color = data.get('color', 'off')

                # ==========================================
                # 🚨 ЛОГИКА ДЕФЕКТА (БРАК) - Мигает КРАСНЫМ
                # ==========================================
                if current_color == 'defect':
                    # Если дефект только что появился
                    if last_color != 'defect':
                        print(f"[{time.strftime('%H:%M:%S')}] 🚨 Станция {station_slug} ➔ БРАК! (Мигает КРАСНЫМ 5 сек)")
                        last_color = 'defect'
                        defect_blink_state = True
                        ser.write(b'R') # Сразу включаем красный
                        defect_timer = time.time() # Засекаем время
                    else:
                        # Если дефект продолжается, проверяем, прошло ли 5 секунд
                        if time.time() - defect_timer >= 5.0:
                            defect_blink_state = not defect_blink_state # Меняем вкл на выкл и наоборот
                            ser.write(b'R' if defect_blink_state else b'O') 
                            defect_timer = time.time() # Снова засекаем 5 секунд

                # ==========================================
                # 🟢 СТАНДАРТНАЯ ЛОГИКА (Обычная работа)
                # ==========================================
                else:
                    if current_color != last_color:
                        if current_color == 'red':
                            ser.write(b'R')
                        elif current_color == 'yellow':
                            ser.write(b'Y')
                        elif current_color == 'green':
                            ser.write(b'G')
                        else:
                            ser.write(b'O') 
                        
                        print(f"[{time.strftime('%H:%M:%S')}] Станция {station_slug} ➔ {current_color.upper()}")
                        last_color = current_color
            else:
                print(f"⚠️ Ошибка сервера: {response.status_code}")
                
            # Ждем 1 секунду перед следующим запросом к серверу
            time.sleep(1) 

        # ==========================================
        # 🛡️ ОТКАЗОУСТОЙЧИВОСТЬ (Защита от сбоев)
        # ==========================================
        except requests.exceptions.RequestException:
            # Если сервер Django упал или пропал Wi-Fi
            if last_color != 'connection_error':
                print(f"[{time.strftime('%H:%M:%S')}] 🚨 Потеряна связь с сервером! Включаю постоянный желтый (Авария).")
                try:
                    ser.write(b'Y')
                except Exception:
                    pass
                last_color = 'connection_error'
            time.sleep(1)
            
        except serial.SerialException:
            # Если от скачка напряжения завис USB-порт
            print(f"[{time.strftime('%H:%M:%S')}] 🔌 Отвалился USB-порт. Переподключаюсь...")
            ser.close()
            ser = connect_arduino(serial_port) 
            last_color = None # Сбрасываем цвет, чтобы принудительно обновить лампу

        except Exception as e:
            # Любая другая непредвиденная ошибка
            print(f"[{time.strftime('%H:%M:%S')}] ⚠️ Ошибка: {e}")
            time.sleep(1)

if __name__ == '__main__':
    main()