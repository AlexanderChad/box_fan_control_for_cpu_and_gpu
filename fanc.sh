#!/bin/bash

DELAY=1
CPU_MIN_TEMP=50
CPU_MAX_TEMP=60
GPU_MIN_TEMP=50
GPU_MAX_TEMP=65
FAN_MIN_SIGNAL=75

CPU_SLOT_NUM=`grep "physical id"  /proc/cpuinfo | sort -u | wc -l`
GPU_CARDS_NUM=`nvidia-smi -L | wc -l`

echo "CPU_SLOT_NUM = $CPU_SLOT_NUM, GPU_CARDS_NUM = $GPU_CARDS_NUM"

echo "Enable manual PWM control"
echo 1 > /sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*/pwm1_enable
echo 1 > /sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*/pwm2_enable

#Returns the maximum value.
function get_max_val {
echo "$1 $2" | awk '{print ($1 > $2) ? $1 : $2}'
}

#Get the maximum temperature among devices. The parameter indicates the type: 0 - CPU, 1 - GPU.
function get_dev_max_temp {
local g_max_temp=0
local dev_slots=$(($1?$GPU_CARDS_NUM:$CPU_SLOT_NUM))
for ((i=0; i<$dev_slots; i++))
do
	local gtemp=$(($1?$(nvidia-smi -i $i --query-gpu=temperature.gpu --format=csv,noheader):$(sensors coretemp-isa-000$i | grep "Package id $i" | sed -r 's/\..+//;s|.*\+||')))
	if [ -z "$gtemp" ]; then
		gtemp=$(($1?$GPU_MAX_TEMP:$CPU_MAX_TEMP))
	fi
	g_max_temp=$(get_max_val $g_max_temp $gtemp)
done
echo $g_max_temp
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

while true
do
#echo "Checking temperatures..."
#echo "$(date +"%d/%m/%y %T")"

cpu_max_temp_val=$(get_dev_max_temp 0)
gpu_max_temp_val=$(get_dev_max_temp 1)

#echo "cpu_max_temp_val = $cpu_max_temp_val"
#echo "gpu_max_temp_val = $gpu_max_temp_val"

cpu_new_pwm_val=$(calc_new_pwm_val $cpu_max_temp_val $CPU_MIN_TEMP $CPU_MAX_TEMP)
gpu_new_pwm_val=$(calc_new_pwm_val $gpu_max_temp_val $GPU_MIN_TEMP $GPU_MAX_TEMP)

#echo "cpu_new_pwm_val = $cpu_new_pwm_val"
#echo "gpu_new_pwm_val = $gpu_new_pwm_val"

case_fan_new_speed=$(get_max_val $cpu_new_pwm_val $gpu_new_pwm_val)
case_fan_old_speed=$(cat /sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*/pwm1)

if (($case_fan_old_speed!=$case_fan_new_speed)); then
	echo "$(date +"%d/%m/%y %T") Checking temperatures..."
	echo "cpu_max_temp_val = $cpu_max_temp_val"
	echo "gpu_max_temp_val = $gpu_max_temp_val"
	echo "PWM: $case_fan_old_speed -> $case_fan_new_speed"
	echo $case_fan_new_speed > /sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*/pwm1
	echo $case_fan_new_speed > /sys/devices/platform/nct6775.2592/hwmon/[[:print:]]*/pwm2
fi

sleep $DELAY

done
