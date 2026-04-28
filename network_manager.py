#!/usr/bin/env python3
"""
Mesh网络管理器 - 处理所有功能实现
"""

import os
from time import time
import fun_GNSS
import UPS_HAT_E.ups as ups
import lora_920_para
import lora_429_para
import dual_lora_controller
from config import LORA_920_CONFIG, LORA_429_CONFIG
import paramiko
import re

class MeshNetworkManager:
    """Mesh网络管理器"""
    
    def show_gnss_info(self):
        """显示GNSS信息"""
        print("\n📍 获取GNSS位置信息...")
        try:
            gnss_info = fun_GNSS.get_gnss_location(timeout=2)
            if gnss_info:
                print("✅ GNSS信息:")
                print(f"   时间: {gnss_info['GNSS_time']}")
                print(f"   位置: {gnss_info['google_lat']:.6f}, {gnss_info['google_lon']:.6f}")
                print(f"   海拔: {gnss_info['altitude']} 米")
                print(f"   速度: {gnss_info['speed']} KM/H")
            else:
                print("❌ 无法获取GNSS信息")
        except Exception as e:
            print(f"❌ GNSS错误: {e}")

    def show_ups_info(self):
        """显示UPS信息"""
        print("\n🔋 获取UPS信息...")
        try:
            ups_info = ups.get_ups_info()
        except Exception as e:
            print(f"❌ UPS错误: {e}")

    def start_lora_920(self):
        """启动920MHz LoRa控制"""
        print("\n📡 启动920MHz LoRa控制...")
        try:
            lora_920_para.lora_920_main(LORA_920_CONFIG)
        except KeyboardInterrupt:
            print("\n返回主菜单...")
        except Exception as e:
            print(f"❌ 920MHz错误: {e}")

    def start_lora_429(self):
        """启动429MHz LoRa控制"""
        print("\n📡 启动429MHz LoRa控制...")
        try:
            lora_429_para.lora_429_main(LORA_429_CONFIG)
        except KeyboardInterrupt:
            print("\n返回主菜单...")
        except Exception as e:
            print(f"❌ 429MHz错误: {e}")

    def start_dual_lora(self):
        """启动双LoRa并行控制"""
        print("\n🔄 启动双LoRa并行控制...")
        try:
            dual_lora_controller.dual_lora_main(LORA_920_CONFIG, LORA_429_CONFIG)
        except KeyboardInterrupt:
            print("\n返回主菜单...")
        except Exception as e:
            print(f"❌ 双LoRa错误: {e}")

    def driot_add_gnss_info(self):
        """为DR-IoT添加GNSS信息"""
        print("\n📍 为DR-IoT添加GNSS信息...")

        # --- 配置信息 ---
        driot_IP = "192.168.98.1"
        driot_USER = "driot"
        driot_PW = "driot"
        REMOTE_LOG_DIR = "./driot_logs" 
        LOCAL_CSV = "merged_gps_data.csv"

        if not os.path.exists(LOCAL_CSV):
            with open(LOCAL_CSV, 'w', encoding='utf-8') as f:
                f.write("Source,Timestamp,Latitude,Longitude,Altitude,Speed,rssi,Data\n")

        while True:
            self.__monitor_remote_logs(driot_IP, driot_USER, driot_PW, REMOTE_LOG_DIR, LOCAL_CSV)

    

    def __monitor_remote_logs(self, driot_IP, driot_USER, driot_PW, REMOTE_LOG_DIR, LOCAL_CSV):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            print(f"正在连接 driot ({driot_IP})...")
            client.connect(driot_IP, username=driot_USER, password=driot_PW, timeout=10)
            
            # --- 修改点 1：去掉 -q，让 tail 输出文件名标志 ---
            remote_cmd = f"tail --follow=name --retry -n 0 {REMOTE_LOG_DIR}/*.log"
            stdin, stdout, stderr = client.exec_command(remote_cmd, get_pty=True)
            
            print("连接成功，开始监控...")
            
            current_file = "unknown" # 用于记录当前正在读取的文件名

            for line in stdout:

                clean_line = line.strip()
                if not clean_line:
                    continue

                # --- 修改点 2：识别 tail 的文件名页眉 ---
                # tail 监控多文件时会输出 ==> ./driot_logs/001.log <==
                if clean_line.startswith("==>") and clean_line.endswith("<=="):
                    # 提取出中间的文件名部分
                    match = re.search(r"==> .*/(.*) <==", clean_line)
                    if match:
                        current_file = match.group(1)
                    continue # 这行是文件名，不作为数据处理，跳过进入下一循环

                rssi_val = "NaN"
                rssi_match = re.search(r"rssi=([^,]+)", clean_line)
                if rssi_match:
                    rssi_val = rssi_match.group(1)

                # 正常数据处理
                try:
                    gnss_info = fun_GNSS.get_gnss_location(timeout=2)
                    if gnss_info:
                        lat = gnss_info['google_lat']
                        lon = gnss_info['google_lon']
                        altitude = gnss_info['altitude']
                        speed = gnss_info['speed']
                        timestamp = gnss_info['GNSS_time']
                    else:
                        lat, lon, altitude, speed, timestamp = "N/A", "N/A", "N/A", "N/A", "N/A"
                except Exception as e:
                    print(f"获取GNSS信息时发生错误: {e}")
                    lat, lon, altitude, speed, timestamp = "N/A", "N/A", "N/A", "N/A", "N/A"

                # --- 修改点 3：将文件名（current_file）作为第一列写入 ---
                output_row = f"{current_file},{timestamp},{lat},{lon},{altitude},{speed},{rssi_val},{clean_line}\n"
                
                with open(LOCAL_CSV, 'a', encoding='utf-8') as f:
                    f.write(output_row)
                
                print(f"[{current_file}] 写入成功: {timestamp}, {lat}, {lon}, {altitude}, {speed}, {rssi_val} ...")

        except Exception as e:
            print(f"发生错误: {e}")
        finally:
            client.close()
            print("连接断开，5秒后尝试重连...")
            time.sleep(5)




