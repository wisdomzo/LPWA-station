import subprocess
import os
import glob
import sys
import time
from threading import Timer
import csv
from datetime import datetime

# The following is to obtain the temprature of the RPi CPU 
def get_cpu_temp():
    # 1. 优先使用 vcgencmd（树莓派官方推荐）
    try:
        output = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
        # 输出格式: temp=51.0'C
        temp_str = output.strip().replace("temp=", "").replace("'C", "")
        return float(temp_str)
    except Exception:
        pass

    # 2. 尝试 hwmon 路径（树莓派5）
    try:
        hwmon_path = glob.glob('/sys/class/hwmon/hwmon*/temp1_input')
        if hwmon_path:
            with open(hwmon_path[0]) as f:
                return float(f.read()) / 1000
    except Exception:
        pass

    # 3. 回退到树莓派4传统路径
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return float(f.read()) / 1000
    except Exception:
        pass

    # 4. 都失败则返回 None
    return None


def get_rssi(node, r_buff):
    # print the rssi
    if node.rssi:
        # print('\x1b[3A',end='\r')
        rssi = -1*(256-r_buff[-1:][0])
        print("The packet RSSI value:\033[1;32m {0}\033[0m dBm".format(rssi))
    else:
        pass
        #print('\x1b[2A',end='\r')
    return rssi


def get_channel_rssi(node):
    node.m0_pin.off()
    node.m1_pin.off()
    time.sleep(0.5)
    node.ser.flushInput()
    node.ser.write(bytes([0xC0,0xC1,0xC2,0xC3,0x00,0x02]))
    time.sleep(0.5)
    re_temp = bytes(5)
    if node.ser.inWaiting() > 0:
        time.sleep(0.1)
        re_temp = node.ser.read(node.ser.inWaiting())
    if re_temp[0] == 0xC1 and re_temp[1] == 0x00 and re_temp[2] == 0x02:
        noisePower = -1*(256-re_temp[3])
        print("The current noise power value:\033[1;31m {0}\033[0m dBm".format(noisePower))
        # print("the last receive packet rssi value: -{0}dBm".format(256-re_temp[4]))
    else:
        # pass
        print("receive power value fail")
        # print("receive rssi value fail: ",re_temp)
    return noisePower


def get_source_and_frequency(node, r_buff):
    source = (r_buff[0]<<8)+r_buff[1]
    frequency = r_buff[2]+node.start_freq
    print("Receive message from node address\033[1;33m %d\033[0m with frequence\033[1;33m %d MHz\033[0m"%(source, frequency), end='\r\n', flush = True)
    return source, frequency


def get_message(r_buff):
    message = bytes(r_buff[3:-1]).decode('utf-8', errors='ignore')
    print("Message is \033[1;33m" + message + "\033[0m", end='\r\n')
    return message


def save_to_csv(filename, source, frequency, message, rssi_dBm, GNSS_time, altitude, lon, lat, speed):
    # 获取当前时间
    # timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    # 分割接收到的message
    parts = message.split(',')
    message = parts[0].strip()
    GNSS_time_tx = parts[1].strip()
    altitude_tx = float(parts[2].strip())
    latitude_tx = float(parts[3].strip())
    longitude_tx = float(parts[4].strip())
    speed_KMpH_tx = float(parts[5].strip())

    # 准备要写入的数据
    data = {
        'source': source,
        'frequency_MHz': frequency,
        'message': message,
        'rssi_dBm': rssi_dBm,
        'GNSS_time_tx': GNSS_time_tx,
        'altitude_tx': altitude_tx,
        'latitude_tx': latitude_tx,
        'longitude_tx': longitude_tx,
        'speed_KMpH_tx': speed_KMpH_tx,
        'GNSS_time_rx': GNSS_time,
        'altitude_rx': altitude,
        'longitude_rx': lon,
        'latitude_rx': lat,
        'speed_KMpH_rx': speed
    }
    
    # 检查文件是否存在，如果不存在则写入表头
    write_header = not os.path.exists(filename)
    
    # 写入CSV文件
    with open(filename, mode='a', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=data.keys())
        if write_header:
            writer.writeheader()
        writer.writerow(data)

    # 使用示例
    # save_to_csv('output.csv', source, frequency, message, rssi_dBm, noisePower_dBm)


def show_meau_function():
    """显示LoRa控制菜单"""
    print("\n=== LoRa 控制菜单 ===")
    print("r 键 - 切换接收功能")
    print("i 键 - 单次发送消息") 
    print("s 键 - 切换连续发送")
    print("d 键 - 显示状态")
    print("Esc 键 - 退出程序")
    print("=====================")



