#!/usr/bin/env python3
"""
Mesh网络配置 - 放在根目录
"""

# LoRa配置
LORA_920_CONFIG = {
    'serial_num': "/dev/ttyAMA3",
    'freq': 920,
    'addr': 1,
    'power': 10,
    'rssi': True,
    'air_speed': 62500,
    'net_id': 0,
    'buffer_size': 240,
    'crypt': 0,
    'relay': False,
    'lbt': False,
    'wor': False,
    'baud_rate': 115200
}

LORA_429_CONFIG = {
    'serial_num': "/dev/ttyAMA4",
    'freq': 429,
    'addr': 1,
    'power': 10,
    'rssi': True,
    'air_speed': 1200,
    'net_id': 0,
    'buffer_size': 240,
    'crypt': 0,
    'relay': False,
    'lbt': False,
    'wor': False,
    'baud_rate': 115200
}