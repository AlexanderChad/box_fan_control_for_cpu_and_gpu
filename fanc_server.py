import pynvml
import threading
import time
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

CONFIG_FILE = "fan_config.json"

# Словарь производителей (Vendor ID -> Имя)
VENDOR_MAP = {
    0x10DE: "NVIDIA Ref.",
    0x1462: "MSI",
    0x1043: "ASUS",
    0x1458: "Gigabyte",
    0x19DA: "ZOTAC",
    0x3842: "EVGA",
    0x1569: "Palit/Galax",
    0x10B0: "Gainward",
    0x196D: "Colorful",
    0x174B: "SYN",
    0x1B4C: "KFA2",
    0x0777: "PNY",
    0x1028: "Dell",
    0x103C: "HP",
    0x17AA: "Lenovo",
}


def get_device_vendor(handle):
    """
    Определяет производителя карты по PCI Subsystem ID.
    """
    try:
        pci_info = pynvml.nvmlDeviceGetPciInfo(handle)
        subsys_id = pci_info.pciSubSystemId

        # Ищем в карте
        vendor_name = VENDOR_MAP.get(subsys_id & 0xFFFF)

        if vendor_name:
            return vendor_name
        else:
            # Если ID не найден, вернем его Hex-значение для справки
            # (например, 0x1234 можно загуглить и добавить в карту)
            return f"Vendor ({hex(subsys_id)})"

    except pynvml.NVMLError:
        return "Unknown"
    except Exception:
        return "Error"


class TemperatureMonitor:
    def __init__(self):
        self.devices = []
        self.lock = threading.Lock()
        self.update_interval = 2  # Интервал опроса температуры
        self.running = True
        self.last_update_time = 0  # Время последнего успешного обновления

    def get_max_temperature(self):
        """Получаем текущую максимальную температуру для HTTP сервера"""
        with self.lock:
            if not self.devices:
                return 0
            return max(d['temp'] for d in self.devices if d['temp'] is not None)

    def get_devices_state(self):
        """Возвращает копию состояния устройств для вентилятора"""
        with self.lock:
            return list(self.devices)

    def detect_devices(self):
        """Сканирует устройства при запуске и печатает информацию"""
        try:
            device_count = pynvml.nvmlDeviceGetCount()
        except pynvml.NVMLError as e:
            print(f"Ошибка NVML при обнаружении устройств: {e}")
            return

        print("Найдены GPU:")
        print("{:<5} | {:<45} | {:<30} | {:<15}".format("ID", "UUID", "Модель", "Производитель"))
        print("-" * 100)

        # Загружаем конфиг, чтобы узнать, сколько профилей применится
        profiles_count = 0
        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            except Exception as e:
                print(f"Ошибка чтения {CONFIG_FILE}: {e}")

        temp_devices = []

        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            uuid = pynvml.nvmlDeviceGetUUID(handle)
            name = pynvml.nvmlDeviceGetName(handle)

            # Декодируем байты если нужно
            if isinstance(uuid, bytes):
                uuid = uuid.decode('utf-8')
            if isinstance(name, bytes):
                name = name.decode('utf-8')

            # Определяем производителя через PCI ID
            vendor = get_device_vendor(handle)

            has_profile = uuid in config
            if has_profile:
                profiles_count += 1

            # Определяем количество вентиляторов
            try:
                num_fans = pynvml.nvmlDeviceGetNumFans(handle)
            except pynvml.NVMLError:
                num_fans = 1  # Fallback, если не удалось узнать количество

            print("{:<5} | {:<45} | {:<30} | {:<15}".format(i, uuid, name, vendor))

            temp_devices.append({
                'uuid': uuid,
                'handle': handle,
                'temp': 0,
                'num_fans': num_fans,
                'has_profile': has_profile,
                'curve': config.get(uuid, [])
            })

        self.devices = temp_devices
        print("-" * 80)
        print(f"Найдены и применены профили для карт: {profiles_count}")

    def update_temperature(self):
        """Основной цикл чтения температур"""
        while self.running:
            try:
                current_time = time.time()

                # Опрашиваем температуры
                with self.lock:
                    for dev in self.devices:
                        temp = pynvml.nvmlDeviceGetTemperature(dev['handle'], pynvml.NVML_TEMPERATURE_GPU)
                        dev['temp'] = temp
                    self.last_update_time = current_time

            except pynvml.NVMLError as e:
                print(f"Ошибка NVML при чтении температуры: {e}")
                # Не обновляем last_update_time, чтобы сработал таймаут в вентиляторе
            except Exception as e:
                print(f"Неожиданная ошибка при чтении температуры: {e}")

            time.sleep(self.update_interval)

    def start(self):
        """Запуск фонового потока"""
        self.thread = threading.Thread(target=self.update_temperature, daemon=True)
        self.thread.start()

    def stop(self):
        """Остановка фонового потока"""
        self.running = False
        self.thread.join(timeout=2)


class FanController:
    def __init__(self, monitor):
        self.monitor = monitor
        self.running = True
        self.update_interval = 2

    def calculate_fan_speed(self, temp, curve):
        """Линейная интерполяция оборотов"""
        curve = sorted(curve, key=lambda x: x[0])
        if temp <= curve[0][0]:
            return curve[0][1]
        if temp >= curve[-1][0]:
            return curve[-1][1]

        for i in range(len(curve) - 1):
            t1, s1 = curve[i]
            t2, s2 = curve[i+1]
            if t1 <= temp <= t2:
                ratio = (temp - t1) / (t2 - t1)
                speed = s1 + (s2 - s1) * ratio
                return int(speed)
        return curve[-1][1]

    def update_fans(self):
        """Функция управления вентиляторами"""
        while self.running:
            # Получаем состояние устройств (копию, чтобы не держать лок долго)
            devices = self.monitor.get_devices_state()
            now = time.time()

            # Проверка таймаута: если данные не обновлялись > 10 сек
            last_update = 0
            with self.monitor.lock:
                last_update = self.monitor.last_update_time

            is_stale = (now - last_update) > 10

            for dev in devices:
                if not dev['has_profile']:
                    continue  # Если профиля нет, не трогаем (оставляем Auto)

                handle = dev['handle']

                # Определяем целевую скорость
                if is_stale:
                    # Если данные устарели, аварийный режим - максимальные обороты
                    target_speed = 100
                else:
                    temp = dev['temp']
                    curve = dev['curve']
                    target_speed = self.calculate_fan_speed(temp, curve)

                # Проходим по всем вентиляторам карты
                for fan_idx in range(dev['num_fans']):
                    try:
                        # Устанавливаем политику в Manual для каждого вентилятора
                        pynvml.nvmlDeviceSetFanControlPolicy(handle, fan_idx, pynvml.NVML_FEATURE_ENABLED)
                        pynvml.nvmlDeviceSetFanSpeed_v2(handle, fan_idx, target_speed)
                    except pynvml.NVMLError as e:
                        # Если конкретный вентилятор не поддерживается или недоступен, игнорируем ошибку,
                        # чтобы не прерывать управление остальными.
                        # Например, некоторые карты имеют фан 0 (основной) и фан 1 (VRM, read-only).
                        pass
                    except Exception:
                        pass

            time.sleep(self.update_interval)

    def reset_all_to_auto(self):
        """Возвращает все управляемые карты в Auto"""
        print("Возврат вентиляторов в автоматический режим...")
        devices = self.monitor.get_devices_state()
        for dev in devices:
            if dev['has_profile']:
                for fan_idx in range(dev['num_fans']):
                    try:
                        pynvml.nvmlDeviceSetFanControlPolicy(dev['handle'], fan_idx, pynvml.NVML_FEATURE_DISABLED)
                    except:
                        pass

    def start(self):
        self.thread = threading.Thread(target=self.update_fans, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join(timeout=2)


class TemperatureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(str(monitor.get_max_temperature()).encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        """Отключаем стандартное логирование запросов"""
        return


if __name__ == '__main__':
    print("Запуск fanc_server...")
    try:
        pynvml.nvmlInit()  # Инициализируем NVML
    except pynvml.NVMLError as e:
        print(f"Не удалось инициализировать NVML: {e}")
        print("Убедитесь, что драйверы NVIDIA установлены и работают.")
        exit(1)  # Завершаем работу, если не можем получить доступ к GPU

    # 1. Создаем монитор и сразу сканируем устройства
    monitor = TemperatureMonitor()
    monitor.detect_devices()

    # 2. Создаем и запускаем контроллер вентиляторов
    fan_controller = FanController(monitor)
    fan_controller.start()

    # 3. Запускаем мониторинг температур
    monitor.start()

    server = HTTPServer(('', 17006), TemperatureHandler)
    print("Сервер мониторинга температуры и управления кулерами запущен на порту 17006")
    try:
        server.serve_forever()
    except:
        print("\nОстановка...")
    finally:
        monitor.stop()
        fan_controller.stop()
        fan_controller.reset_all_to_auto()
        server.server_close()
        pynvml.nvmlShutdown()
        print("Сервер остановлен")
