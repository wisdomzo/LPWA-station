#!/usr/bin/env python3
"""
简洁版Mesh网络 - 增强版（包含RSSI信息）
"""

import time
import json
import threading
import logging
from datetime import datetime
from config import LORA_429_CONFIG

class SimpleMesh:
    """简洁的Mesh网络实现 - 增强版"""
    
    def __init__(self, node_id):
        self.node_id = node_id
        # 增强：邻居信息现在包含RSSI和时间戳 {node_id: {'last_seen': timestamp, 'rssi': rssi_value, 'rssi_samples': []}}
        self.neighbors = {}
        self.running = False
        self.lora_node = None

        # 🔧 IoT优化参数
        self.hello_interval = 60          # HELLO间隔：60秒（1分钟）
        self.neighbor_timeout = 180       # 邻居超时：180秒（3分钟）
        self.cleaner_interval = 30        # 清理间隔：30秒

        # 🆕 初始化日志系统
        self._setup_logging()

        self.log("🟢 Mesh节点初始化...")
        self._initialize_lora()
    
    def _setup_logging(self):
        """🆕 新增：设置统一的日志系统"""
        # 创建logger
        self.logger = logging.getLogger(f'MeshNode_{self.node_id}')
        self.logger.setLevel(logging.INFO)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            # 文件handler - 输出到log.txt
            file_handler = logging.FileHandler('log.txt', encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            
            # 控制台handler - 同时输出到控制台
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 设置日志格式
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            # 添加handler
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

    def log(self, message, level='info'):
        """🆕 新增：统一的日志记录方法"""
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(message)
            
    def _initialize_lora(self):
        """初始化LoRa模块并设置回调"""
        try:
            from sx126x_429 import sx126x
            
            self.lora_node = sx126x(
                serial_num=LORA_429_CONFIG.get('serial_num', "/dev/ttyAMA3"),
                freq=LORA_429_CONFIG.get('freq', 920),
                addr=self.node_id,
                power=LORA_429_CONFIG.get('power', 10),
                rssi=LORA_429_CONFIG.get('rssi', True),
                air_speed=LORA_429_CONFIG.get('air_speed', 62500),
                net_id=LORA_429_CONFIG.get('net_id', 0),
                buffer_size=LORA_429_CONFIG.get('buffer_size', 240),
                crypt=LORA_429_CONFIG.get('crypt', 0),
                relay=LORA_429_CONFIG.get('relay', False),
                lbt=LORA_429_CONFIG.get('lbt', False),
                wor=LORA_429_CONFIG.get('wor', False),
                baud_rate=LORA_429_CONFIG.get('baud_rate', 115200)
            )
            
            # 设置Mesh消息回调
            self.lora_node.set_mesh_callback(self._mesh_message_handler)
            self.log("✅ LoRa模块初始化完成")
            
        except Exception as e:
            error_msg = f"❌ LoRa初始化失败: {e}"
            self.log(error_msg, 'error')
            raise
    
    def _mesh_message_handler(self, message_str, rssi, source_addr):
        """Mesh消息处理回调"""
        try:
            message = json.loads(message_str)
            self._handle_mesh_message(message, source_addr, rssi)
        except json.JSONDecodeError:
            error_msg = f"❌ Mesh消息JSON解析失败: {message_str}"
            self.log(error_msg, 'error')
        except Exception as e:
            error_msg = f"❌ Mesh消息处理错误: {e}"
            self.log(error_msg, 'error')
    
    def _handle_mesh_message(self, message, source_addr, rssi):
        """处理Mesh消息"""
        msg_type = message.get('type')
        sender_id = message.get('node_id')
        
        if not sender_id or sender_id == self.node_id:
            return  # 忽略无效或自己的消息

        # 🎯 修改：检查消息是否针对本节点
        target_id = message.get('target')
        if target_id and target_id != self.node_id and target_id != 0xFFFF:
            # 这不是发给我的单播消息，忽略
            self.log(f"📨 收到非目标消息: {msg_type} 来自 {sender_id} (目标: {target_id})", 'debug')
            return
        
        self.log(f"📨 Mesh消息: {msg_type} 来自 {sender_id}, RSSI: {rssi}dBm")
        
        # 🔄 增强：更新邻居信息时包含RSSI
        self._update_neighbor(sender_id, rssi)
        
        if msg_type == 'HELLO':
            self._handle_hello(sender_id, message, rssi)
        elif msg_type == 'PING':
            self._handle_ping(sender_id, message, rssi)
        elif msg_type == 'PONG':
            self._handle_pong(sender_id, message, rssi)
        else:
            warn_msg = f"⚠️ 未知Mesh消息类型: {msg_type}"
            self.log(warn_msg, 'warning')
    
    def _update_neighbor(self, neighbor_id, rssi):
        """🔧 新增：更新邻居信息，包含RSSI"""
        current_time = time.time()
        
        if neighbor_id not in self.neighbors:
            self.neighbors[neighbor_id] = {
                'last_seen': current_time,
                'rssi': rssi,
                'rssi_samples': [rssi],  # 存储最近的RSSI样本
                'first_seen': current_time
            }
            info_msg = f"🎉 发现新邻居: {neighbor_id}, 初始RSSI: {rssi}dBm"
            self.log(info_msg)
        else:
            # 更新现有邻居信息
            neighbor = self.neighbors[neighbor_id]
            neighbor['last_seen'] = current_time
            
            # 维护最近的RSSI样本（最多10个）
            neighbor['rssi_samples'].append(rssi)
            if len(neighbor['rssi_samples']) > 10:
                neighbor['rssi_samples'].pop(0)
            
            # 计算平均RSSI
            avg_rssi = sum(neighbor['rssi_samples']) / len(neighbor['rssi_samples'])
            neighbor['rssi'] = avg_rssi

            info_msg = f"🔄 更新邻居: {neighbor_id}, 平均RSSI: {avg_rssi:.1f}dBm"
            self.log(info_msg)
    
    def _handle_hello(self, sender_id, message, rssi):
        """处理HELLO消息 - 增强：包含RSSI信息"""
        # 邻居信息已在 _update_neighbor 中更新
        neighbors_list = list(self.neighbors.keys())
        self.log(f"   当前邻居: {neighbors_list}")
    
    def _handle_ping(self, sender_id, message, rssi):
        """处理PING消息 - 增强：包含RSSI信息"""
        if message.get('target') == self.node_id:
            info_msg = f"✅ 响应PING来自 {sender_id}, RSSI: {rssi}dBm"
            self.log(info_msg)
            self.send_pong(sender_id, message.get('seq'))
        else:
            info_msg = f"📨 收到PING来自 {sender_id} (目标不是我), RSSI: {rssi}dBm"
            self.log(info_msg)
    
    def _handle_pong(self, sender_id, message, rssi):
        """处理PONG消息 - 增强：包含RSSI信息"""
        info_msg = f"✅ 收到PONG来自 {sender_id}, RSSI: {rssi}dBm"
        self.log(info_msg)
    
    def start(self):
        """启动Mesh网络"""
        if self.running:
            return
            
        self.running = True
        
        # 启动工作线程
        threads = [
            threading.Thread(target=self._hello_worker, daemon=True),
            threading.Thread(target=self._cleaner_worker, daemon=True),
            threading.Thread(target=self._receive_worker, daemon=True)
        ]
        
        for thread in threads:
            thread.start()
        
        self.log(f"🟢 Mesh节点 {self.node_id} 已启动")
    
    def stop(self):
        """停止Mesh网络"""
        self.running = False
        self.log(f"🔴 Mesh节点 {self.node_id} 已停止")
    
    def _hello_worker(self):
        """HELLO消息广播"""
        count = 0
        while self.running:
            try:
                self.send_hello(count)
                count += 1
                time.sleep(self.hello_interval)
            except Exception as e:
                error_msg = f"❌ HELLO广播错误: {e}"
                self.log(error_msg, 'error')
                time.sleep(5)
    
    def _cleaner_worker(self):
        """清理过期邻居"""
        while self.running:
            try:
                current_time = time.time()
                expired = [nid for nid, info in self.neighbors.items() 
                          if current_time - info['last_seen'] > self.neighbor_timeout]
                
                for neighbor_id in expired:
                    del self.neighbors[neighbor_id]
                    info_msg = f"🗑️ 邻居 {neighbor_id} 超时移除"
                    self.log(info_msg)
                
                time.sleep(self.cleaner_interval)
            except Exception as e:
                error_msg = f"❌ 邻居清理错误: {e}"
                self.log(error_msg, 'error')
                time.sleep(5)
    
    def _receive_worker(self):
        """接收工作线程"""
        while self.running:
            try:
                self.lora_node.receive()
                time.sleep(0.1)
            except Exception as e:
                error_msg = f"❌ 接收错误: {e}"
                self.log(error_msg, 'error')
                time.sleep(1)
    
    def send_hello(self, seq=0):
        """发送HELLO消息"""
        message = {
            'type': 'HELLO',
            'node_id': self.node_id,
            'timestamp': time.time(),
            'seq': seq
        }
        self._send_via_lora(message)  # 广播，不指定target_id
    
    def send_ping(self, target_id):
        """发送PING消息 - 改为单播"""
        if target_id not in self.neighbors:
            warn_msg = f"⚠️ 目标节点 {target_id} 不在邻居列表中"
            self.log(warn_msg, 'warning')
            return False
            
        message = {
            'type': 'PING',
            'node_id': self.node_id,
            'target': target_id,
            'timestamp': time.time(),
            'seq': int(time.time())
        }
        
        # 🎯 修改：指定目标节点单播
        success = self._send_via_lora(message, target_id=target_id)
        return success
    
    def send_pong(self, target_id, in_reply_to):
        """发送PONG响应 - 改为单播"""
        message = {
            'type': 'PONG',
            'node_id': self.node_id,
            'target': target_id,
            'timestamp': time.time(),
            'in_reply_to': in_reply_to
        }
        # 🎯 修改：指定目标节点单播
        self._send_via_lora(message, target_id=target_id)
    
    def _send_via_lora(self, message_dict, target_id=None):
        """通过LoRa发送消息
        Args:
        message_dict: 消息字典
        target_id: 目标节点ID，None表示广播
        """
        try:
            message_str = json.dumps(message_dict, ensure_ascii=False)

            # 🎯 修改：支持单播和广播
            if target_id is None:
                # 广播：目标地址为0xFFFF
                target_addr = 0xFFFF
                log_type = "广播"
            else:
                # 单播：目标地址为具体的节点ID
                target_addr = target_id
                log_type = f"单播到{target_id}"
            
            data = (
                bytes([target_addr >> 8]) +
                bytes([target_addr & 0xff]) +
                bytes([self.lora_node.offset_freq]) +
                bytes([self.node_id >> 8]) +
                bytes([self.node_id & 0xff]) +
                bytes([self.lora_node.offset_freq]) +
                message_str.encode('utf-8')
            )
            
            self.lora_node.send(data)
            self.log(f"📤 {log_type}发送: {message_dict['type']}")
            return True
            
        except Exception as e:
            error_msg = f"❌ 发送失败: {e}"
            self.log(error_msg, 'error')
            return False
    
    def get_status(self):
        """🔧 增强：获取状态，包含RSSI信息"""
        neighbor_details = {}
        for nid, info in self.neighbors.items():
            neighbor_details[nid] = {
                'rssi': info['rssi'],
                'last_seen': time.strftime('%H:%M:%S', time.localtime(info['last_seen'])),
                'age': int(time.time() - info['last_seen']),
                'sample_count': len(info['rssi_samples'])
            }
        
        return {
            'node_id': self.node_id,
            'neighbors': list(self.neighbors.keys()),
            'neighbor_details': neighbor_details,
            'neighbor_count': len(self.neighbors),
            'running': self.running
        }
    
    def print_status(self):
        """🔧 增强：打印状态，显示RSSI信息"""
        status = self.get_status()
        status_msg = f"\n=== Mesh节点 {self.node_id} ==="
        status_msg += f"\n状态: {'🟢 运行中' if status['running'] else '🔴 已停止'}"
        status_msg += f"\n邻居数量: {status['neighbor_count']}个"
        
        if status['neighbor_details']:
            status_msg += "\n邻居详情:"
            for nid, details in status['neighbor_details'].items():
                status_msg += f"\n  {nid}: RSSI={details['rssi']:.1f}dBm, 年龄={details['age']}s, 样本={details['sample_count']}"
        else:
            status_msg += "\n邻居: 无"
        status_msg += "\n" + "=" * 30

        # 同时输出到控制台和日志文件
        print(status_msg)
        self.log(status_msg.replace('\n', ' | '))  # 日志文件中用 | 分隔多行
    
    def get_best_neighbor(self):
        """🔧 新增：获取信号最好的邻居（用于路由决策）"""
        if not self.neighbors:
            return None
        
        # 选择RSSI最强的邻居（RSSI值越大表示信号越好）
        best_neighbor = max(self.neighbors.items(), key=lambda x: x[1]['rssi'])
        return best_neighbor[0], best_neighbor[1]['rssi']




def main():
    """主函数"""
    print("🧪 简洁版Mesh网络 - 增强版（含RSSI）")
    print("=" * 50)
    
    try:
        node_id = int(input("请输入节点ID (1-1000): ") or "1")
        
        mesh = SimpleMesh(node_id)
        mesh.start()
        
        print(f"\n✅ 节点 {node_id} 已启动!")
        print("   等待发现邻居...")
        print("   按Ctrl+C停止\n")
        
        try:
            while mesh.running:
                cmd = input("命令 (s=状态, p ID=PING, b=最佳邻居, q=退出): ").strip().lower()
                
                if cmd == 's':
                    mesh.print_status()
                elif cmd.startswith('p '):
                    parts = cmd.split()
                    if len(parts) == 2 and parts[1].isdigit():
                        mesh.send_ping(int(parts[1]))
                elif cmd == 'b':
                    best = mesh.get_best_neighbor()
                    if best:
                        result_msg = f"📡 最佳邻居: 节点{best[0]}, RSSI: {best[1]:.1f}dBm"
                        print(result_msg)
                        mesh.log(result_msg)
                    else:
                        result_msg = "📡 暂无邻居"
                        print(result_msg)
                        mesh.log(result_msg)
                elif cmd == 'q':
                    break
                    
        except KeyboardInterrupt:
            print("\n🛑 用户中断")
        finally:
            mesh.stop()
            
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    main()