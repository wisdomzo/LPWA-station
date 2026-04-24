#!/usr/bin/env python3
"""
简洁版Mesh网络 - 增强版（包含RSSI信息和路由功能）
"""

import time
import json
import threading
import logging
import numpy as np  # 🆕 新增：用于RSSI标准差计算
from datetime import datetime
from config import LORA_429_CONFIG


class RoutingTable:
    """🆕 路由表管理类"""
    
    def __init__(self, node_id):
        self.node_id = node_id
        self.routes = {}  # {destination: route_info}
        self.route_seq = 0

    def update_route(self, dest, next_hop, metric, hop_count, seq_num=None):
        """更新路由表项"""
        current_time = time.time()

        # 🎯 新增：直接邻居特殊处理
        if hop_count == 1:
            # 直接邻居总是更新
            if dest not in self.routes:
                # 新路由
                self.routes[dest] = {
                    'next_hop': next_hop,
                    'metric': metric,
                    'hop_count': hop_count,
                    'seq': 0,  # 序列号不重要
                    'last_updated': current_time,
                    'destination': dest
                }
                return True
            else:
                # 现有路由：更新时间戳，可更新度量值
                self.routes[dest]['last_updated'] = current_time
                self.routes[dest]['metric'] = metric  # 更新度量值
                return True  # 🎯 总是返回True，表示时间戳已更新

        # 🎯 多跳路由：保持原有逻辑（但可以简化）
        if seq_num is None:
            seq_num = self._get_next_seq()
            
        # 检查是否是新路由或更好的路由
        if dest not in self.routes:
            self.routes[dest] = {}
            
        current_route = self.routes.get(dest, {})

        # 简化：只比较序列号
        should_update = (dest == self.node_id or seq_num > current_route.get('seq', -1))
        
        if should_update:
            self.routes[dest] = {
                'next_hop': next_hop,
                'metric': metric,
                'hop_count': hop_count,
                'seq': seq_num,
                'last_updated': current_time,
                'destination': dest
            }
        
        return should_update
    
    def get_best_route(self, dest):
        """获取到目标的最佳路由"""
        if dest in self.routes:
            return self.routes[dest]
        return None
    
    def remove_route(self, dest):
        """移除路由 - 增强日志"""
        if dest in self.routes:
            del self.routes[dest]
            return True
        return False  # 🆕 返回是否实际移除了路由
    
    def get_all_routes(self):
        """获取所有路由"""
        return self.routes.copy()
    
    def get_reachable_nodes(self):
        """获取所有可达节点（不包括自己）"""
        return [node for node in self.routes.keys() if node != self.node_id]
    
    def get_direct_neighbor_routes(self):
        """获取所有直接邻居的路由"""
        direct_routes = {}
        for dest, route in self.routes.items():
            if route['hop_count'] == 1 and dest != self.node_id:
                direct_routes[dest] = route
        return direct_routes
    
    def _get_next_seq(self):
        """获取下一个序列号"""
        self.route_seq += 1
        return self.route_seq
    
    def cleanup_expired_routes(self, timeout_seconds):
        """🆕 明确：只清理过期的多跳路由（直接路由由邻居管理）"""
        current_time = time.time()
        expired = []
        
        for dest, route in self.routes.items():
            # 跳过：自己的路由、直接邻居路由（由邻居管理）
            if dest == self.node_id or route['hop_count'] == 1:
                continue
                
            # 只检查多跳路由的超时
            if current_time - route['last_updated'] > timeout_seconds:
                expired.append(dest)
        
        for dest in expired:
            self.remove_route(dest)
            
        return expired
    
    def print_routing_table(self):
        """打印路由表（用于调试）"""
        if not self.routes:
            return "路由表为空"
            
        table_str = "路由表:\n"
        table_str += "目标节点 -> 下一跳 | 度量值 | 跳数 | 年龄\n"
        table_str += "-" * 50 + "\n"
        
        current_time = time.time()
        for dest, route in sorted(self.routes.items()):
            if dest == self.node_id:
                continue  # 跳过显示到自己的路由
                
            age = int(current_time - route['last_updated'])
            table_str += f"{dest:^8} -> {route['next_hop']:^8} | {route['metric']:.3f} | {route['hop_count']:^4} | {age:^3}秒\n"
        
        return table_str
    
    def get_route_statistics(self):
        """获取路由统计信息"""
        total_routes = len(self.routes)
        direct_routes = len(self.get_direct_neighbor_routes())
        multi_hop_routes = total_routes - direct_routes - 1  # 减去到自己的路由
        
        avg_metric = 0
        if total_routes > 1:  # 排除到自己的路由
            metrics = [route['metric'] for dest, route in self.routes.items() if dest != self.node_id]
            avg_metric = sum(metrics) / len(metrics) if metrics else 0
        
        return {
            'total_routes': total_routes - 1,  # 不统计到自己的路由
            'direct_routes': direct_routes,
            'multi_hop_routes': multi_hop_routes,
            'avg_metric': round(avg_metric, 3)
        }


# 🆕 新增路由计算函数
def calculate_link_quality(rssi):
    """针对LoRa优化的链路质量计算"""
    # 参数基于典型LoRa模块特性
    EXCELLENT_THRESHOLD = -60   # 优秀：>-60dBm
    GOOD_THRESHOLD = -80        # 良好：-60 ~ -80dBm  
    FAIR_THRESHOLD = -100       # 可用：-80 ~ -100dBm
    WEAK_THRESHOLD = -115       # 边缘：-100 ~ -115dBm
    MIN_RSSI = -120             # 最小可用的RSSI
    
    if rssi >= EXCELLENT_THRESHOLD:
        # 优秀信号，接近饱和
        return 1.0
    elif rssi >= GOOD_THRESHOLD:
        # 良好信号，线性过渡
        return 0.8 + 0.2 * (rssi - GOOD_THRESHOLD) / (EXCELLENT_THRESHOLD - GOOD_THRESHOLD)
    elif rssi >= FAIR_THRESHOLD:
        # 可用信号，质量中等
        return 0.5 + 0.3 * (rssi - FAIR_THRESHOLD) / (GOOD_THRESHOLD - FAIR_THRESHOLD)
    elif rssi >= WEAK_THRESHOLD:
        # 边缘信号，质量较低但仍可用
        return 0.2 + 0.3 * (rssi - WEAK_THRESHOLD) / (FAIR_THRESHOLD - WEAK_THRESHOLD)
    elif rssi >= MIN_RSSI:
        # 临界信号，接近灵敏度极限
        return 0.05 + 0.15 * (rssi - MIN_RSSI) / (WEAK_THRESHOLD - MIN_RSSI)
    else:
        # 低于灵敏度极限，不可用
        return 0.0
    

def calculate_route_metric(rssi, hop_count, stability, is_bidirectional=False):
    """计算路由度量值"""
    link_quality = calculate_link_quality(rssi)
    hop_penalty = 0.7 ** (hop_count - 1)
    stability_score = min(1.0, stability)
    
    # 🆕 双向性奖励
    bidirectional_bonus = 1.2 if is_bidirectional else 0.8
    metric = (link_quality * 0.6 + hop_penalty * 0.3 + stability_score * 0.1) * bidirectional_bonus
    return round(metric, 3)



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

        # 🆕 Stage 2.1 新增：路由参数
        self.route_update_interval = 30   # 路由更新间隔：30秒
        self.route_timeout = 300          # 路由超时：300秒（5分钟）
        self.route_seq = 0                # 路由序列号
        self.bidirectional_threshold = -75  # 🆕 双向链路RSSI阈值

        # 🆕 初始化路由表
        self.routing_table = RoutingTable(self.node_id)

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
        """🆕 修改：支持单向路由，但优选双向路由"""
        current_time = time.time()
        
        # 🆕 检测双向性
        is_bidirectional = self._check_bidirectional(neighbor_id, rssi)
        
        if neighbor_id not in self.neighbors:
            # 新邻居 - 立即建立路由
            stability = 1.0  # 新连接，初始稳定性
            route_metric = calculate_route_metric(rssi, 1, stability, is_bidirectional)
            
            self.neighbors[neighbor_id] = {
                'last_seen': current_time,
                'rssi': rssi,
                'rssi_samples': [rssi],
                'first_seen': current_time,
                'link_quality': calculate_link_quality(rssi),
                'hop_count': 1,
                'route_metric': route_metric,
                'next_hop': neighbor_id,
                'route_seq': self.route_seq,
                'is_direct': True,
                'bidirectional': is_bidirectional,  # 🆕 新增双向标记
                'stability': stability
            }
            
            # 更新路由表
            self.routing_table.update_route(
                dest=neighbor_id,
                next_hop=neighbor_id,
                metric=route_metric,
                hop_count=1
            )
            
            neighbor_type = "双向" if is_bidirectional else "单向"
            info_msg = f"🎉 发现{neighbor_type}邻居: {neighbor_id}, RSSI: {rssi}dBm, 度量: {route_metric:.3f}"
            self.log(info_msg)
            
        else:
            # 更新现有邻居
            neighbor = self.neighbors[neighbor_id]
            neighbor['last_seen'] = current_time
            
            # 更新RSSI样本
            neighbor['rssi_samples'].append(rssi)
            if len(neighbor['rssi_samples']) > 10:
                neighbor['rssi_samples'].pop(0)
            
            # 重新计算
            avg_rssi = sum(neighbor['rssi_samples']) / len(neighbor['rssi_samples'])
            neighbor['rssi'] = avg_rssi
            
            # 🆕 重新评估双向性
            was_bidirectional = neighbor.get('bidirectional', False)
            is_bidirectional_now = self._check_bidirectional(neighbor_id, avg_rssi)
            neighbor['bidirectional'] = is_bidirectional_now
            
            # 更新稳定性
            stability = self._calculate_stability(neighbor_id)
            neighbor['stability'] = stability
            neighbor['link_quality'] = calculate_link_quality(avg_rssi)
            
            # 重新计算路由度量
            route_metric = calculate_route_metric(avg_rssi, 1, stability, is_bidirectional_now)
            neighbor['route_metric'] = route_metric
            
            # 更新路由表
            self.routing_table.update_route(
                dest=neighbor_id,
                next_hop=neighbor_id,
                metric=route_metric,
                hop_count=1
            )

            # 🆕 记录状态变化
            if is_bidirectional_now and not was_bidirectional:
                self.log(f"🔄 邻居 {neighbor_id} 升级为双向连接")
            elif not is_bidirectional_now and was_bidirectional:
                self.log(f"⚠️ 邻居 {neighbor_id} 降级为单向连接")
                
            info_msg = f"🔄 更新邻居: {neighbor_id}, RSSI: {avg_rssi:.1f}dBm, 度量: {route_metric:.3f}, {'双向' if is_bidirectional_now else '单向'}"
            self.log(info_msg)
    
    def _check_bidirectional(self, neighbor_id, rssi):
        """🆕 新增：检查是否为双向链路（简化版）
        TODO: Stage 2.2中实现完整方案
        完整方案需要：
        1. 交换路由信息
        2. 检查邻居路由表是否包含自己
        3. 主动验证机制
        
        当前简化版仅基于RSSI阈值，实际效果有限。
        但在Stage 2.1中足够，因为：
        - 主要测试直接邻居通信
        - Stage 2.2会重构此功能
        - 避免过度设计
        """
        # 在实际实现中，这需要复杂的双向检测机制
        # 当前简化版：基于RSSI阈值判断
        return rssi > self.bidirectional_threshold

    def _calculate_stability(self, neighbor_id):
        """🆕 新增：计算邻居连接稳定性"""
        if neighbor_id not in self.neighbors:
            return 0.0
            
        neighbor = self.neighbors[neighbor_id]
        current_time = time.time()
        
        # 基于连接时长
        connection_duration = current_time - neighbor['first_seen']
        duration_stability = min(1.0, connection_duration / 300)  # 5分钟达到最大
        
        # 基于样本数量
        sample_count = len(neighbor['rssi_samples'])
        sample_stability = min(1.0, sample_count / 10)
        
        # 基于信号稳定性（RSSI方差）
        if len(neighbor['rssi_samples']) > 1:
            rssi_std = np.std(neighbor['rssi_samples'])
            rssi_variance = max(0, 1 - (rssi_std / 20))  # 标准差越小越稳定
        else:
            rssi_variance = 0.5
            
        stability = (duration_stability * 0.4 + sample_stability * 0.3 + rssi_variance * 0.3)
        return round(stability, 2)

    def get_intelligent_route(self, dest):
        """🆕 新增：智能路由选择，优选双向路径"""
        if dest == self.node_id:
            return {'next_hop': self.node_id, 'metric': 1.0, 'hop_count': 0}
        
        direct_route = self.routing_table.get_best_route(dest)
        if not direct_route:
            return None
        
        # 如果是直接邻居，检查链路质量
        if direct_route['hop_count'] == 1:
            next_hop = direct_route['next_hop']
            if next_hop in self.neighbors:
                neighbor = self.neighbors[next_hop]
                if neighbor.get('bidirectional', False) and neighbor['route_metric'] > 0.5:
                    return direct_route  # 优秀：高质量双向直接路由
                else:
                    self.log(f"⚠️ 到 {dest} 的直接路径质量较低，寻找替代路径")
        
        return direct_route  # 返回最佳可用路由

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
            threading.Thread(target=self._receive_worker, daemon=True),
            # 🆕 新增路由维护线程
            threading.Thread(target=self._route_maintenance_worker, daemon=True)
        ]
        
        for thread in threads:
            thread.start()
        
        self.log(f"🟢 Mesh节点 {self.node_id} 已启动 (Stage 2.1 路由支持)")
    
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
        """增强：清理过期邻居和对应路由"""
        while self.running:
            try:
                current_time = time.time()
                expired_neighbors = []

                # 找出所有过期的邻居
                for nid, info in self.neighbors.items():
                    if current_time - info['last_seen'] > self.neighbor_timeout:
                        expired_neighbors.append(nid)

                # 清理过期邻居及其路由
                for neighbor_id in expired_neighbors:
                    # 1. 从邻居表移除
                    del self.neighbors[neighbor_id]

                    # 🆕 2. 从路由表移除对应的直接路由
                    route_removed = self.routing_table.remove_route(neighbor_id)
                    if route_removed:
                        self.log(f"🗑️ 同步移除邻居 {neighbor_id} 的路由")
                    else:
                        self.log(f"🗑️ 邻居 {neighbor_id} 超时移除 (无对应路由)")

                    info_msg = f"🗑️ 邻居 {neighbor_id} 超时移除"
                    self.log(info_msg)

                # 🆕 3. 额外清理多跳路由（保持原有功能）
                expired_routes = self.routing_table.cleanup_expired_routes(self.route_timeout)
                for route_dest in expired_routes:
                    self.log(f"🗑️ 多跳路由超时移除: {route_dest}")

                time.sleep(self.cleaner_interval)
            except Exception as e:
                self.log(f"❌ 邻居清理错误: {e}", 'error')
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

    def _route_maintenance_worker(self):
        """🆕 简化：路由维护工作线程（邻居清理已处理直接路由）"""
        while self.running:
            try:
                # 🆕 现在只需要清理多跳路由，直接路由由邻居清理线程处理
                expired_routes = self.routing_table.cleanup_expired_routes(self.route_timeout)
                for route_dest in expired_routes:
                    self.log(f"🗑️ 多跳路由超时移除: {route_dest}")
                
                # 🆕 确保到自己的路由存在
                self.routing_table.update_route(
                    dest=self.node_id,
                    next_hop=self.node_id,
                    metric=1.0,
                    hop_count=0
                )
                
                # 🆕 定期记录路由统计（可选，避免日志过多）
                stats = self.routing_table.get_route_statistics()
                if stats['total_routes'] > 0 and time.time() % 60 < 5:  # 每分钟记录一次
                    self.log(f"📊 路由统计: 总计{stats['total_routes']}条, 直接{stats['direct_routes']}条, 多跳{stats['multi_hop_routes']}条, 平均度量{stats['avg_metric']:.3f}")
                
                time.sleep(self.cleaner_interval)
            except Exception as e:
                self.log(f"❌ 路由维护错误: {e}", 'error')
                time.sleep(5)
    
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
        """🔧 增强：获取状态，包含RSSI和路由信息"""
        neighbor_details = {}
        for nid, info in self.neighbors.items():
            neighbor_details[nid] = {
                'rssi': info['rssi'],
                'last_seen': time.strftime('%H:%M:%S', time.localtime(info['last_seen'])),
                'age': int(time.time() - info['last_seen']),
                'sample_count': len(info['rssi_samples']),
                # 🆕 新增路由信息
                'link_quality': info.get('link_quality', 0),
                'route_metric': info.get('route_metric', 0),
                'bidirectional': info.get('bidirectional', False),
                'stability': info.get('stability', 0),
                'is_direct': info.get('is_direct', True)
            }
        
        # 🆕 获取路由表信息
        route_details = {}
        for dest, route in self.routing_table.get_all_routes().items():
            route_details[dest] = {
                'next_hop': route['next_hop'],
                'metric': route['metric'],
                'hop_count': route['hop_count'],
                'age': int(time.time() - route['last_updated'])
            }
        
        # 🆕 获取路由统计
        route_stats = self.routing_table.get_route_statistics()
        
        return {
            'node_id': self.node_id,
            'neighbors': list(self.neighbors.keys()),
            'neighbor_details': neighbor_details,
            'neighbor_count': len(self.neighbors),
            # 🆕 新增路由信息
            'routes': route_details,
            'route_count': len(route_details),
            'reachable_nodes': self.routing_table.get_reachable_nodes(),
            'route_statistics': route_stats,
            'running': self.running
        }
    
    def print_status(self):
        """🔧 增强：打印状态，显示RSSI和路由信息"""
        status = self.get_status()
        status_msg = f"\n=== Mesh节点 {self.node_id} ==="
        status_msg += f"\n状态: {'🟢 运行中' if status['running'] else '🔴 已停止'}"
        status_msg += f"\n邻居数量: {status['neighbor_count']}个"
        status_msg += f"\n路由数量: {status['route_count']}个"
        
        if status['neighbor_details']:
            status_msg += "\n邻居详情:"
            for nid, details in status['neighbor_details'].items():
                link_type = "🟢" if details['bidirectional'] else "🟡"
                status_msg += f"\n  {link_type} {nid}: RSSI={details['rssi']:.1f}dBm, 年龄={details['age']}s, 质量={details['link_quality']:.2f}, 稳定={details['stability']:.2f}, 度量={details['route_metric']:.3f}"
        else:
            status_msg += "\n邻居: 无"
        
        # 🆕 显示路由表
        if status['routes']:
            status_msg += "\n路由表:"
            for dest, route in status['routes'].items():
                if dest != self.node_id:  # 不显示到自己的路由
                    status_msg += f"\n  到 {dest}: 下一跳={route['next_hop']}, 度量={route['metric']:.3f}, 跳数={route['hop_count']}, 年龄={route['age']}s"
        else:
            status_msg += "\n路由: 无"
            
        # 🆕 显示路由统计
        stats = status['route_statistics']
        status_msg += f"\n路由统计: 总计{stats['total_routes']}条, 直接{stats['direct_routes']}条, 多跳{stats['multi_hop_routes']}条"
        
        status_msg += "\n" + "=" * 30

        # 同时输出到控制台和日志文件
        print(status_msg)
        self.log(status_msg.replace('\n', ' | '))
    
    def get_best_neighbor(self):
        """🔧 新增：获取信号最好的邻居（用于路由决策）"""
        if not self.neighbors:
            return None
        
        # 选择RSSI最强的邻居（RSSI值越大表示信号越好）
        best_neighbor = max(self.neighbors.items(), key=lambda x: x[1]['rssi'])
        return best_neighbor[0], best_neighbor[1]['rssi']




def main():
    """主函数"""
    print("🧪 简洁版Mesh网络 - 增强版（含RSSI和路由）")
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
                cmd = input("命令 (s=状态, p ID=PING, b=最佳邻居, r=路由表, rstats=路由统计, route=智能路由, q=退出): ").strip().lower()
                
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
                elif cmd == 'r':
                    # 🆕 显示详细路由表
                    print("\n" + mesh.routing_table.print_routing_table())
                elif cmd == 'rstats':
                    # 🆕 显示路由统计
                    stats = mesh.routing_table.get_route_statistics()
                    print(f"\n📊 路由统计:")
                    print(f"   总路由数: {stats['total_routes']}")
                    print(f"   直接路由: {stats['direct_routes']}")
                    print(f"   多跳路由: {stats['multi_hop_routes']}")
                    print(f"   平均度量: {stats['avg_metric']:.3f}")
                elif cmd == 'route':
                    # 🆕 测试智能路由
                    target = input("目标节点ID: ").strip()
                    if target.isdigit():
                        route = mesh.get_intelligent_route(int(target))
                        if route:
                            print(f"📍 到节点{target}的智能路由:")
                            print(f"   下一跳: {route['next_hop']}")
                            print(f"   度量值: {route['metric']:.3f}")
                            print(f"   跳数: {route['hop_count']}")
                        else:
                            print(f"❌ 没有到节点{target}的路由")
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