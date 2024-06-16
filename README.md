# box_fan_control_for_cpu_and_gpu

Проект представляет собой реализацию простого сервиса для автоматического управления кулерами на материнской плате.  
Умеет определять количество CPU и GPU. Выбирает самый горячий процессор из каждого типа и устанавливает скорость на основе максимально нуждающегося в охлаждении. GPU поддерживаются только Nvidia (необходима утилита `nvidia-smi`).  
НЕ управляет оборотами кулеров видеокарт (для безопасности), только читает температуру.  
Тестировалось на плате `MACHINIST X99 D8 MAX` с двумя `Nvidia RTX 2080 Ti`, `Proxmox VE 8.2`.  

## Установка и настройка  
1. Скачать и перейти в папку `box_fan_control_for_cpu_and_gpu`:
	```
	git clone https://github.com/AlexanderChad/box_fan_control_for_cpu_and_gpu.git
	cd box_fan_control_for_cpu_and_gpu
	```
1. Заменить в `fanc.service` путь до файла `fanc.sh` на свой, например:
	```
	- ExecStart=/home/fanc.sh
	+ ExecStart=/home/alex/box_fan_control_for_cpu_and_gpu/fanc.sh
	```
1. Убедиться в наличии и правильной работе утилиты `nvidia-smi`. При ее отсутсвии установить/обновить драйвера видеокарты Nvidia.  
1. В `fanc.sh` установить предпочитаемые настройки:  
	* `DELAY=1` - время между проверками  
	* `CPU_MIN_TEMP=50` - минимальная температура CPU, до этой температуры PWM сигнал будет минимальный (`FAN_MIN_SIGNAL`)  
	* `CPU_MAX_TEMP=60` - максимальная температура CPU, при ней и выше обороты будут максимальными  
	* `GPU_MIN_TEMP=50` - минимальная температура GPU, до этой температуры PWM сигнал будет минимальный (`FAN_MIN_SIGNAL`)  
	* `GPU_MAX_TEMP=65` - максимальная температура GPU, при ней и выше обороты будут максимальными  
	* `FAN_MIN_SIGNAL=75` - минимальный сигнал PWM (порог), при котором куллеры будут вращаться (ниже которого связь сигнал-обороты пропадает).  
	
	Узнать `FAN_MIN_SIGNAL` можно с помощью `pwmconfig` из пакета `fancontrol` или подобрать экспериментально.  
	С помощью той же утилиты можно найти прямые пути до точек управления кулерами.  
	Их необходимо будет заменить на ваши, например:  
	```
	- echo 1 > /sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*/pwm1_enable
	+ echo 1 > /sys/devices/platform/coretemp.0/hwmon/[[:print:]]*/pwm0_enable
	- echo 1 > /sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*/pwm2_enable
	+ echo 1 > /sys/devices/platform/coretemp.0/hwmon/[[:print:]]*/pwm1_enable
	```  
	Аналогично для строк установки оборотов кулеров:  
	```
	- echo $case_fan_new_speed > /sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*/pwm1
	+ echo $case_fan_new_speed > /sys/devices/platform/coretemp.0/hwmon/[[:print:]]*/pwm0
	- echo $case_fan_new_speed > /sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*/pwm2
	+ echo $case_fan_new_speed > /sys/devices/platform/coretemp.0/hwmon/[[:print:]]*/pwm1
	```  
1. Разрешить выполнение `fanc.sh`:  
	```
	chmod +x fanc.sh
	```  
1. Запустить `fanc.sh` и убедится в корректности работы:  
	```
	./fanc.sh
	```  
1. Зарегистрировать сервис, добавить в автозапуск, запустить и проверить статус:  
	```
	systemctl enable '/home/alex/box_fan_control_for_cpu_and_gpu/fanc.service'
	systemctl daemon-reload
	systemctl start fanc
	systemctl status fanc
	```  
	В статусе после удачного запуска должно быть:  
	```
		● fanc.service - Fan control
		Loaded: loaded (/etc/systemd/system/fanc.service; enabled; preset: enabled)
		Active: active (running) since Sun 2024-06-16 23:26:03 +07; 6s ago
		Main PID: 1469146 (fanc.sh)
		Tasks: 2 (limit: 154467)
		Memory: 5.5M
			CPU: 696ms
		CGroup: /system.slice/fanc.service
				├─1469146 /bin/bash /home/fanc.sh
				└─1469452 sleep 1
	
	Jun 16 23:26:03 aes systemd[1]: Started fanc.service - Fan control.
	Jun 16 23:26:03 aes fanc.sh[1469146]: CPU_SLOT_NUM = 2, GPU_CARDS_NUM = 2
	Jun 16 23:26:03 aes fanc.sh[1469146]: Enable manual PWM control
	Jun 16 23:26:03 aes fanc.sh[1469146]: Start PWM control task
	```  
	Во время работы, при изменении оборотов кулеров, должны появляться следующие строчки:
	```
	Jun 16 23:34:05 aes fanc.sh[1469146]: gpu_max_temp_val = 53
	Jun 16 23:34:05 aes fanc.sh[1469146]: PWM: 87 -> 111
	Jun 16 23:34:06 aes fanc.sh[1469146]: 16/06/24 23:34:06 Checking temperatures...
	Jun 16 23:34:06 aes fanc.sh[1469146]: cpu_max_temp_val = 42
	Jun 16 23:34:06 aes fanc.sh[1469146]: gpu_max_temp_val = 54
	Jun 16 23:34:06 aes fanc.sh[1469146]: PWM: 111 -> 123
	Jun 16 23:34:07 aes fanc.sh[1469146]: 16/06/24 23:34:07 Checking temperatures...
	Jun 16 23:34:07 aes fanc.sh[1469146]: cpu_max_temp_val = 42
	Jun 16 23:34:07 aes fanc.sh[1469146]: gpu_max_temp_val = 55
	Jun 16 23:34:07 aes fanc.sh[1469146]: PWM: 123 -> 135
	```  

## Демонстрация:  
[![Проверяю охлаждение сервера (ЦП и видеокарт)](https://i.ytimg.com/vi/YAdFYVp97Wk/hq720_2.jpg)](https://youtube.com/shorts/YAdFYVp97Wk?feature=share)  

### <b><font color="#FF0000">Предупреждение!</font></b>  
Неправильная работа серсиса может вызвать перегрев и выход из строя компонентов или системы в целом.  
Хоть код и имеет некоторую защиту (при возврате вместо температуры пустой строки выводит обороты на максимум), но не учитывает других случаев, например:  
* нулевого количества устройств (если получение информации завершилось ошибкой)  
* аномальных значений (если функция возвращает число с невозможной температурой)  
* не установлены пакеты, содержащие `nvidia-smi` и `sensors` или они неправильно работают (не настроены)  
* сервис не обладает повышенным приоритетом, хотя, учитывая его роль, должен.  

А так же некоторые другие. Возможно в будущем я вернусь к этому и добавлю проверки.  
Пока же это можете сделать вы или использовать как есть на свой страх и риск.  

### Совместимость  
Проверено на  `MACHINIST X99 D8 MAX` с двумя `Nvidia RTX 2080 Ti`, `Proxmox VE 8.2`, но должно работать после настройки и на других дистрибутивах / оборудовании.

[Заметка на Дзене](https://dzen.ru/b/ZiELJLmPUiH7RN4i)  
