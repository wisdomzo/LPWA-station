#!/usr/bin/python
# -*- coding: UTF-8 -*-

import sys
import termios
import tty
import time
import select
import threading
import lora_920_para
import lora_429_para

old_settings = termios.tcgetattr(sys.stdin)
tty.setcbreak(sys.stdin.fileno())

class DualLoRaController:
    def __init__(self, config1, config2):
        self.config1 = config1
        self.config2 = config2
        self.lora_920 = None
        self.lora_429 = None
        self.lora_920_handler = None
        self.lora_429_handler = None
        self.running = False
        self.control_thread = None
        
    def initialize_modules(self):
        """初始化两个LoRa模块"""
        try:
            print("正在初始化LoRa 920 MHz模块...")
            # 初始化920MHz模块
            self.lora_920 = lora_920_para.sx126x.sx126x(
                serial_num = self.config1.get('serial_num', "/dev/ttyAMA3"),
                freq = self.config1.get('freq', 920),
                addr = self.config1.get('addr', 1),
                power = self.config1.get('power', 10),
                rssi = self.config1.get('rssi', True),
                air_speed = self.config1.get('air_speed', 62500),
                net_id = self.config1.get('net_id', 0),
                buffer_size = self.config1.get('buffer_size', 240),
                crypt = self.config1.get('crypt', 0),
                relay = self.config1.get('relay', False),
                lbt = self.config1.get('lbt', False),
                wor = self.config1.get('wor', False),
                baud_rate = self.config1.get('baud_rate', 115200)
            )
            self.lora_920_handler = lora_920_para.LoRaHandler(self.lora_920)
            
            print("正在初始化LoRa 429 MHz模块...")
            # 初始化429MHz模块
            self.lora_429 = lora_429_para.sx126x_429.sx126x(
                serial_num = self.config2.get('serial_num', "/dev/ttyAMA4"),
                freq = self.config2.get('freq', 429),
                addr = self.config2.get('addr', 1),
                power = self.config2.get('power', 10),
                rssi = self.config2.get('rssi', True),
                air_speed = self.config2.get('air_speed', 62500),
                net_id = self.config2.get('net_id', 0),
                buffer_size = self.config2.get('buffer_size', 240),
                crypt = self.config2.get('crypt', 0),
                relay = self.config2.get('relay', False),
                lbt = self.config2.get('lbt', False),
                wor = self.config2.get('wor', False),
                baud_rate = self.config2.get('baud_rate', 115200)
            )
            self.lora_429_handler = lora_429_para.LoRaHandler(self.lora_429)
            
            print("\033[1;32m✓ 双LoRa模块初始化完成\033[0m")
            return True
            
        except Exception as e:
            print(f"\033[1;31m初始化失败: {e}\033[0m")
            return False
    
    def start_dual_receive(self):
        """同时启动两个模块的接收功能"""
        if not self.lora_920_handler or not self.lora_429_handler:
            print("LoRa模块未初始化")
            return False
            
        print("\033[1;32m启动双频段接收模式...\033[0m")
        print("920MHz: 接收中...")
        print("429MHz: 接收中...")
        
        self.lora_920_handler.start_receive()
        self.lora_429_handler.start_receive()
        
        return True
    
    def start_dual_transmit(self, interval=5):
        """同时启动两个模块的发送功能"""
        if not self.lora_920_handler or not self.lora_429_handler:
            print("LoRa模块未初始化")
            return False
            
        print(f"\033[1;32m启动双频段发送模式，间隔: {interval}秒...\033[0m")
        print("920MHz: 发送中...")
        print("429MHz: 发送中...")
        
        self.lora_920_handler.start_send_continuous(interval)
        self.lora_429_handler.start_send_continuous(interval)
        
        return True
    
    def stop_dual_operations(self):
        """停止所有操作"""
        print("\033[1;33m停止所有LoRa操作...\033[0m")
        
        if self.lora_920_handler:
            self.lora_920_handler.stop_all()
        if self.lora_429_handler:
            self.lora_429_handler.stop_all()
    
    def get_status(self):
        """显示双模块状态"""
        if not self.lora_920_handler or not self.lora_429_handler:
            print("\033[1;31m模块未初始化\033[0m")
            return
        
        # 获取频率值
        freq_920 = self.lora_920.freq
        freq_429 = self.lora_429.freq
        
        # 920MHz模块状态
        status_920_rec = "\033[1;32m运行中\033[0m" if self.lora_920_handler.receiving else "\033[1;31m已停止\033[0m"
        status_920_send = "\033[1;32m运行中\033[0m" if self.lora_920_handler.sending else "\033[1;31m已停止\033[0m"
        
        # 429MHz模块状态
        status_429_rec = "\033[1;32m运行中\033[0m" if self.lora_429_handler.receiving else "\033[1;31m已停止\033[0m"
        status_429_send = "\033[1;32m运行中\033[0m" if self.lora_429_handler.sending else "\033[1;31m已停止\033[0m"
        
        print("\n" + "="*40)
        print("          双LoRa模块状态")
        print("="*40)
        print(f"\033[1;36m{freq_920}MHz模块:\033[0m")
        print(f"  接收功能: {status_920_rec}")
        print(f"  发送功能: {status_920_send}") 
        print(f"  本地地址: {self.lora_920.addr}")
        print(f"  频率: {freq_920} MHz")
        print()
        print(f"\033[1;35m{freq_429}MHz模块:\033[0m")
        print(f"  接收功能: {status_429_rec}")
        print(f"  发送功能: {status_429_send}")
        print(f"  本地地址: {self.lora_429.addr}")
        print(f"  频率: {freq_429} MHz")
        print("="*40)

def dual_lora_main(config1, config2):
    """双LoRa模块主控制函数"""
    controller = DualLoRaController(config1, config2)
    
    # 初始化模块
    if not controller.initialize_modules():
        print("双LoRa模块初始化失败，请检查硬件连接")
        return
    
    try:
        print("\n" + "="*50)
        print("          双LoRa模块并行控制")
        print("="*50)
        print("1. 启动双频段接收(Rx)模式")
        print("2. 启动双频段发送(Tx)模式")
        print("3. 停止所有操作")
        print("4. 显示状态")
        print("Esc. 退出双LoRa控制")
        print("="*50)
        
        while True:
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                c = sys.stdin.read(1)
                
                # 退出键
                if c == '\x1b':
                    print("退出双LoRa控制...")
                    break
                
                # 选项1: 双接收
                elif c == '\x31':  # '1'
                    controller.start_dual_receive()
                
                # 选项2: 双发送
                elif c == '\x32':  # '2'
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
                    controller.start_dual_transmit(interval)
                
                # 选项3: 停止所有
                elif c == '\x33':  # '3'
                    controller.stop_dual_operations()
                
                # 选项4: 显示状态
                elif c == '\x34':  # '4'
                    controller.get_status()
                
                sys.stdout.flush()
                
            # 短暂休眠避免过度占用CPU
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"程序错误: {e}")
    finally:
        # 清理资源
        controller.stop_dual_operations()
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)