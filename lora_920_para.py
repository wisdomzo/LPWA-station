#!/usr/bin/python
# -*- coding: UTF-8 -*-

#
#    this is an UART-LoRa device and thers is an firmware on Module
#    users can transfer or receive the data directly by UART and dont
#    need to set parameters like coderate,spread factor,etc.
#    |============================================ |
#    |   It does not suport LoRaWAN protocol !!!   |
#    | ============================================|
#   
#    This script is mainly for Raspberry Pi 3B+, 4B, Zero, 5 series
#    Since PC/Laptop does not have GPIO to control HAT, it should be configured by
#    GUI and while setting the jumpers.
#
#   serial_num
#       PiZero, Pi3B+, and Pi4B use "/dev/ttyS0"
#
#    Frequency is [850 to 930], or [410 to 493] MHz
#
#    address is 0 to 65535
#        under the same frequence,if set 65535,the node can receive 
#        messages from another node of address is 0 to 65534 and similarly,
#        the address 0 to 65534 of node can receive messages while 
#        the another note of address is 65535 sends.
#        otherwise two node must be same the address and frequence
#
#    The tramsmit power is {10, 13, 17, and 22} dBm
#
#    RSSI (receive signal strength indicator) is {True or False}
#        It will print the RSSI value when it receives each message
#
# #######################################
# 2025/10/25 Ver.1.2.0 by zhaoou

import sys
import termios
from threading import Timer
import tty
import sx126x
import time
import select
import fun_GNSS
import threading
import queue

old_settings = termios.tcgetattr(sys.stdin)
tty.setcbreak(sys.stdin.fileno())


def send_deal(node):
    get_rec = ""
    print("请输入格式为：\033[1;33m1, 868, Hello World\033[0m")
    print("含义：目标地址 = 1, 频率 = 868 MHz, 内容 = Hello World")
    print("请按 Enter 提交：", end='', flush=True)

    # 逐字符读取直到按下 Enter（0x0A 是换行）
    while True:
        ch = sys.stdin.read(1)
        if ch == '\x0a':
            break
        get_rec += ch
        sys.stdout.write(ch)
        sys.stdout.flush()

    # 拆分参数
    try:
        get_t = [x.strip() for x in get_rec.split(",")]
        target_addr = int(get_t[0])
        freq = int(get_t[1])
        message = get_t[2]
    except Exception as e:
        print(f"\n\033[1;31m输入格式错误，请重新输入。错误信息：{e}\033[0m")
        return
    
    # 计算频率偏移
    base_freq = 850 if freq >= 850 else 410
    offset_freq = freq - base_freq

    # 添加GNSS信息
    gnssInfo = fun_GNSS.get_gnss_location(timeout = 1)
    GNSS_time = gnssInfo["GNSS_time"]
    altitude = gnssInfo["altitude"]
    lon = gnssInfo["google_lon"]
    lat = gnssInfo["google_lat"]
    speed = gnssInfo["speed"]
    message = message + "," + GNSS_time + "," + str(altitude) + "," + str(lon) + "," + str(lat) + "," + str(speed)

    # 构建数据帧
    data = (
        bytes([target_addr >> 8]) +
        bytes([target_addr & 0xff]) +
        bytes([offset_freq]) +
        bytes([node.addr >> 8]) +
        bytes([node.addr & 0xff]) +
        bytes([node.offset_freq]) +
        message.encode()
    )

    #
    # the sending message format
    #
    #         receiving node              receiving node                   receiving node           own high 8bit           own low 8bit                 own 
    #         high 8bit address           low 8bit address                    frequency                address                 address                  frequency             message payload

    node.send(data)
    print("\n")


def send_cpu_continue(node):
    """简化版本的连续发送函数"""
    message = "Tx GNSS info"
    gnssInfo = fun_GNSS.get_gnss_location(timeout=1)
    if gnssInfo:
        GNSS_time = gnssInfo["GNSS_time"]
        altitude = gnssInfo["altitude"]
        lon = gnssInfo["google_lon"]
        lat = gnssInfo["google_lat"]
        speed = gnssInfo["speed"]
    else:
        GNSS_time = "N/A"
        altitude = -999
        lon = -999
        lat = -999
        speed = -999
    temp_str = message + "," + GNSS_time + "," + str(altitude) + "," + str(lon) + "," + str(lat) + "," + str(speed)
    
    addr_high = (node.addr >> 8) & 0xFF
    addr_low = node.addr & 0xFF
    freq_offset = node.offset_freq
    
    data = (bytes([0xFF, 0xFF, freq_offset, addr_high, addr_low, freq_offset]) + temp_str.encode('utf-8'))
    node.send(data)
    print(f"[{time.strftime('%H:%M:%S')}] 已发送GNSS数据")


class LoRaHandler:
    def __init__(self, node):
        self.node = node
        self.receiving = False
        self.sending = False
        self.receive_thread = None
        self.send_thread = None
        self.send_queue = queue.Queue()
        self.stop_event = threading.Event()

    def start_receive(self):
        """启动接收线程"""
        if self.receiving:
            print("接收功能已在运行中")
            return
        
        self.receiving = True
        self.receive_thread = threading.Thread(target=self._receive_worker, daemon=True)
        self.receive_thread.start()
        print("\033[1;32m✓ 接收功能已启动\033[0m")

    def stop_receive(self):
        """停止接收线程"""
        if self.receiving:
            self.receiving = False
            if self.receive_thread and self.receive_thread.is_alive():
                self.receive_thread.join(timeout=1)
            print("\033[1;33m接收功能已停止\033[0m")

    def start_send_continuous(self, interval=5):
        """启动连续发送线程"""
        if self.sending:
            print("发送功能已在运行中")
            return
        
        self.sending = True
        self.send_thread = threading.Thread(target=self._send_worker, daemon=True, args=(interval,))
        self.send_thread.start()
        print(f"\033[1;32m✓ 自动发送已启动，间隔: {interval}秒\033[0m")

    def stop_send_continuous(self):
        """停止连续发送线程"""
        if self.sending:
            self.sending = False
            if self.send_thread and self.send_thread.is_alive():
                self.send_thread.join(timeout=1)
            print("\033[1;33m自动发送已停止\033[0m")

    def send_single_message(self, target_addr, freq, message):
        """发送单条消息"""
        try:
            # 计算频率偏移
            base_freq = 850 if freq >= 850 else 410
            offset_freq = freq - base_freq

            # 添加GNSS信息
            gnssInfo = fun_GNSS.get_gnss_location(timeout=1)
            if gnssInfo:
                GNSS_time = gnssInfo["GNSS_time"]
                altitude = gnssInfo["altitude"]
                lon = gnssInfo["google_lon"]
                lat = gnssInfo["google_lat"]
                speed = gnssInfo["speed"]
            else:
                GNSS_time = "N/A"
                altitude = -999
                lon = -999
                lat = -999
                speed = -999
            full_message = message + "," + GNSS_time + "," + str(altitude) + "," + str(lon) + "," + str(lat) + "," + str(speed)

            # 构建数据帧
            data = (
                bytes([target_addr >> 8]) +
                bytes([target_addr & 0xff]) +
                bytes([offset_freq]) +
                bytes([self.node.addr >> 8]) +
                bytes([self.node.addr & 0xff]) +
                bytes([self.node.offset_freq]) +
                full_message.encode()
            )

            self.node.send(data)
            print(f"\033[1;32m✓ 消息已发送: {message}\033[0m")
            
        except Exception as e:
            print(f"\033[1;31m发送失败: {e}\033[0m")

    def _receive_worker(self):
        """接收工作线程"""
        while self.receiving and not self.stop_event.is_set():
            try:
                self.node.receive()
                # 添加小的延迟避免过度占用CPU
                time.sleep(0.1)
            except Exception as e:
                print(f"接收错误: {e}")
                time.sleep(1)

    def _send_worker(self, interval):
        """发送工作线程"""
        while self.sending and not self.stop_event.is_set():
            try:
                send_cpu_continue(self.node)
                # 等待指定间隔，但期间可以响应停止事件
                for _ in range(interval * 10):
                    if not self.sending or self.stop_event.is_set():
                        break
                    time.sleep(0.1)
            except Exception as e:
                print(f"发送错误: {e}")
                time.sleep(1)

    def stop_all(self):
        """停止所有线程"""
        self.stop_event.set()
        self.receiving = False
        self.sending = False
        
        # 等待线程结束
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1)
        if self.send_thread and self.send_thread.is_alive():
            self.send_thread.join(timeout=1)
            
        print("所有LoRa任务已停止")


def lora_920_main(config):
    # 串口设备名（根据你实际的连接来改）
    serial_port = config.get('serial_num', "/dev/ttyAMA3")

    # 初始化 LoRa 模块
    node = sx126x.sx126x(
        serial_num = serial_port,
        freq = config.get('freq', 920),             # MHz
        addr = config.get('addr', 1),          # 本地地址
        power = config.get('power', 10),             # 发射功率 dBm
        rssi = config.get('rssi', True),           # 是否显示RSSI
        air_speed = config.get('air_speed', 62500),       # 空中速率 in bps
        net_id = config.get('net_id', 0),             # 网络ID
        buffer_size = config.get('buffer_size', 240),    # 缓冲区大小 in Byte
        crypt = config.get('crypt', 0),              # 加密字节
        relay = config.get('relay', False),          # 中继模式
        lbt = config.get('lbt', False),            # Listen Before Talk
        wor = config.get('wor', False),             # 唤醒功能
        baud_rate = config.get('baud_rate', 115200)     # Baud rate in bps. 
    )

    # 创建LoRa处理器
    lora_handler = LoRaHandler(node)

    try:
        # 更新菜单显示
        print("\n=== LoRa 控制菜单 ===")
        print("r 键 - 切换接收功能")
        print("i 键 - 单次发送消息") 
        print("s 键 - 切换连续发送")
        print("d 键 - 显示状态")
        print("Esc 键 - 退出程序")
        print("=====================")
        
        while True:
            
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                c = sys.stdin.read(1)

                # dectect key Esc
                if c == '\x1b': 
                    lora_handler.stop_all()
                    break

                # 检测 r 键 - 切换接收功能
                elif c == '\x72':  # 'r'
                    if lora_handler.receiving:
                        lora_handler.stop_receive()
                    else:
                        lora_handler.start_receive()

                # dectect key i - 单次发送
                elif c == '\x69':  # 'i'
                    print("请输入格式为：\033[1;33m1, 868, Hello World\033[0m")
                    print("含义：目标地址 = 1, 频率 = 868 MHz, 内容 = Hello World")
                    print("请按 Enter 提交：", end='', flush=True)
                    
                    # 读取用户输入
                    user_input = ""
                    while True:
                        ch = sys.stdin.read(1)
                        if ch == '\x0a':  # Enter键
                            break
                        user_input += ch
                        sys.stdout.write(ch)
                        sys.stdout.flush()
                    
                    # 处理输入
                    try:
                        get_t = [x.strip() for x in user_input.split(",")]
                        target_addr = int(get_t[0])
                        freq = int(get_t[1])
                        message = get_t[2]
                        lora_handler.send_single_message(target_addr, freq, message)
                    except Exception as e:
                        print(f"\n\033[1;31m输入格式错误: {e}\033[0m")

                # 检测 s 键 - 切换连续发送
                elif c == '\x73':  # 's'
                    if lora_handler.sending:
                        lora_handler.stop_send_continuous()
                    else:
                        # 获取发送间隔
                        print("请输入发送间隔(秒，默认5): ", end='', flush=True)
                        interval_input = ""
                        while True:
                            ch = sys.stdin.read(1)
                            if ch == '\x0a':  # Enter键
                                break
                            interval_input += ch
                            sys.stdout.write(ch)
                            sys.stdout.flush()
                        
                        interval = int(interval_input) if interval_input.isdigit() else 5
                        lora_handler.start_send_continuous(interval)

                # 检测 d 键 - 显示状态
                elif c == '\x64':  # 'd'
                    receive_status = "\033[1;32m运行中\033[0m" if lora_handler.receiving else "\033[1;31m已停止\033[0m"
                    send_status = "\033[1;32m运行中\033[0m" if lora_handler.sending else "\033[1;31m已停止\033[0m"
                    print(f"\n=== LoRa状态 ===")
                    print(f"接收功能: {receive_status}")
                    print(f"发送功能: {send_status}")
                    print(f"本地地址: {node.addr}")
                    print(f"频率: {node.freq} MHz")
                    print("=================")

                sys.stdout.flush() 

    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序错误: {e}")
    finally:
        lora_handler.stop_all()
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    return