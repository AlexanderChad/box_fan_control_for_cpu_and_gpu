#!/usr/bin/env bash

DELAY=2 #Delay between checks
CPU_MIN_TEMP=50 #CPU min temp
CPU_MAX_TEMP=60 #CPU max temp
GPU_MIN_TEMP=50 #GPU min temp
GPU_MAX_TEMP=65 #GPU max temp
FAN_MIN_SIGNAL=75 #Min PWM value

ANOMAL_MIN_TEMP=5 #Anomal min temp
ANOMAL_MAX_TEMP=90 #Anomal max temp

# Список серверов мониторинга GPU (IP:PORT)
gpu_temp_servers=("192.168.5.2:17006" "192.168.5.3:17006")

CPU_SLOT_NUM=$(grep "physical id"  /proc/cpuinfo | sort -u | wc -l)

FAN_CTRL_PATH='/sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*'

echo "CPU_SLOT_NUM = $CPU_SLOT_NUM, GPU servers: ${#gpu_temp_servers[@]}"

echo "Enable manual PWM control"
echo 1 > $FAN_CTRL_PATH/pwm1_enable
echo 1 > $FAN_CTRL_PATH/pwm2_enable

#Set the fan PWM value
function set_fan_pwm_val {
	echo $1 > $FAN_CTRL_PATH/pwm1
	echo $1 > $FAN_CTRL_PATH/pwm2
}

#Checking CPU devices
if [ -z "$CPU_SLOT_NUM" ] || ((CPU_SLOT_NUM==0)); then
	echo "ERROR! No CPU devices found."
	set_fan_pwm_val 255
	while true
	do
	sleep $DELAY
	done
fi

#Returns the maximum value.
function get_max_val {
echo "$1 $2" | awk '{print ($1 > $2) ? $1 : $2}'
}

#Get CPU temperature
function get_cpu_temp {
local g_max_temp=0
for ((i=0; i<CPU_SLOT_NUM; i++))
do
	#Get temperature from CPU
	local gtemp=$(sensors coretemp-isa-000$i | grep "Package id $i" | sed -r 's/\..+//;s|.*\+||')
	#Checking temperature
	if [ -z "$gtemp" ] || (($gtemp<$ANOMAL_MIN_TEMP)) || (($gtemp>$ANOMAL_MAX_TEMP)); then
		#If temperature is not valid - set maximum value
		gtemp=$CPU_MAX_TEMP
	fi
	#Save maximum value
	g_max_temp=$(get_max_val $g_max_temp $gtemp)
done
echo $g_max_temp
}

#Get GPU temperature from servers
function get_gpu_temp {
local g_max_temp=0
local got_response=0

# Если нет серверов - возвращаем минимальное значение (для отсутствия реакции)
if [ ${#gpu_temp_servers[@]} -eq 0 ]; then
	echo $GPU_MIN_TEMP
	return
fi

for server in "${gpu_temp_servers[@]}"
do
	# Получаем температуру с сервера
	local temp=$(curl -m 0.5 -s "http://$server/")
	# Проверяем что ответ - валидное число
	if [[ "$temp" =~ ^[0-9]+$ ]]; then
		# Если получили ответ - сохраняем максимум
		g_max_temp=$(get_max_val $g_max_temp $temp)
		got_response=1
	fi
done

# Если получили хоть один ответ - возвращаем максимум из всех
if [ $got_response -eq 1 ]; then
	# Проверяем, что полученное значение в пределах допустимых
	if (($g_max_temp<$ANOMAL_MIN_TEMP)) || (($g_max_temp>$ANOMAL_MAX_TEMP)); then
		# Если не в пределах - возвращаем максимальное значение
		g_max_temp=$GPU_MAX_TEMP
	fi
	echo $g_max_temp
else
	# Ни один сервер не ответил - возвращаем минимальное значение (для отсутствия реакции)
	echo $GPU_MIN_TEMP
fi
}

#Calc new pwm from temperature. 1 - temp, 2 - min_temp, 3 - max_temp.
function calc_new_pwm_val {
if (($1<=$2)); then
echo $FAN_MIN_SIGNAL
elif (($1>=$3)); then
echo 255
else
echo $(((255-$FAN_MIN_SIGNAL)*($1-$2)/($3-$2)+$FAN_MIN_SIGNAL))
fi
}

echo "Start PWM control task"

cpu_max_temp_val_old=$CPU_MIN_TEMP
gpu_max_temp_val_old=$GPU_MIN_TEMP
cpu_new_pwm_val=$FAN_MIN_SIGNAL
gpu_new_pwm_val=$FAN_MIN_SIGNAL

while true
do

#Get CPU and GPU temperatures
cpu_max_temp_val=$(get_cpu_temp)
gpu_max_temp_val=$(get_gpu_temp)

#Checking changes for CPU and calc new pwm values
if ((cpu_max_temp_val != cpu_max_temp_val_old)); then
	cpu_max_temp_val_old=$cpu_max_temp_val
	cpu_new_pwm_val=$(calc_new_pwm_val $cpu_max_temp_val $CPU_MIN_TEMP $CPU_MAX_TEMP)
fi

#Checking changes for GPU and calc new pwm values
if [ "$gpu_max_temp_val" != "NONE" ] && ((gpu_max_temp_val != gpu_max_temp_val_old)); then
	gpu_max_temp_val_old=$gpu_max_temp_val
	gpu_new_pwm_val=$(calc_new_pwm_val $gpu_max_temp_val $GPU_MIN_TEMP $GPU_MAX_TEMP)
fi

case_fan_new_speed=$(get_max_val $cpu_new_pwm_val $gpu_new_pwm_val)
case_fan_now_speed=$(cat $FAN_CTRL_PATH/pwm1)

if (($case_fan_now_speed != $case_fan_new_speed)); then
	echo "$(date +"%d/%m/%y %T") Checking temperatures..."
	echo "cpu_max_temp_val = $cpu_max_temp_val"
	echo "gpu_max_temp_val = $gpu_max_temp_val"
	echo "PWM: $case_fan_now_speed -> $case_fan_new_speed"
	set_fan_pwm_val $case_fan_new_speed
fi

sleep $DELAY

done