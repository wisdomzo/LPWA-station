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

    def update_route(self, dest, next_hop, metric, hop_count, seq_num=None, is_bidirectional=False):
        """更新路由表项"""
        current_time = time.time()

        # 新增：非双向路由特殊处理
        if not is_bidirectional and hop_count > 1:
            return False

        # 直接邻居特殊处理
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
                    'destination': dest,
                    'is_bidirectional': is_bidirectional
                }
                return True
            else:
                # 现有路由：更新时间戳，可更新度量值
                self.routes[dest]['last_updated'] = current_time
                self.routes[dest]['metric'] = metric  # 更新度量值
                self.routes[dest]['is_bidirectional'] = is_bidirectional
                return True  # 🎯 总是返回True，表示时间戳已更新

        # 🎯 多跳路由：保持原有逻辑（但可以简化）
        if seq_num is None:
            seq_num = self._get_next_seq()
            
        # 检查是否是新路由或更好的路由
        if dest not in self.routes:
            self.routes[dest] = {}
            
        current_route = self.routes.get(dest, {})

        # 比较旧路由是否应该更新
        should_update = (
            dest == self.node_id 
            or seq_num > current_route.get('seq', -1)
            or current_route.get('last_updated') != current_time
            )
        
        if should_update:
            self.routes[dest] = {
                'next_hop': next_hop,
                'metric': metric,
                'hop_count': hop_count,
                'seq': seq_num,
                'last_updated': current_time,
                'destination': dest,
                'is_bidirectional': is_bidirectional 
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
        # 增强：邻居信息现在包含RSSI和时间戳 {node_id: {'last_seen': ts, 'rssi': rssi_value, 'rssi_samples': []}}
        self.neighbors = {}
        self.running = False
        self.lora_node = None

        # 🔧 IoT优化参数
        self.hello_interval = 60          # HELLO间隔：60秒（1分钟）
        self.neighbor_timeout = 180       # 邻居超时：180秒（3分钟）
        self.cleaner_interval = 30        # 清理间隔：30秒

        # 🆕 Stage 2.1 新增：路由参数
        self.route_update_interval = 130   # 路由更新间隔：30秒
        self.route_timeout = 300          # 路由超时：300秒（5分钟）
        self.route_seq = 0                # 路由序列号
        self.bidirectional_threshold = -85  # 🆕 双向链路RSSI阈值
        self.MAX_HOP_COUNT = 4

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
        self.log(f"📨 Mesh消息: {msg_type} 来自 {sender_id}, RSSI: {rssi}dBm")

        # 更新邻居信息时包含RSSI
        if message.get('is_routed'):
            pass
        else:
            self._update_neighbor(sender_id, rssi)
        
        if msg_type == 'HELLO':
            self._handle_hello(sender_id, message, rssi)
        elif msg_type == 'PING':
            self._handle_ping(sender_id, message, rssi)
        elif msg_type == 'PONG':
            self._handle_pong(sender_id, message, rssi)
        # 🆕 Stage 2.2 第1步：添加ROUTE_UPDATE (RU) 处理
        elif msg_type == 'RU':
            self._handle_route_update(sender_id, message, rssi)
        else:
            warn_msg = f"⚠️ 未知Mesh消息类型: {msg_type}"
            self.log(warn_msg, 'warning')
    
    def _handle_route_update(self, sender_id, message, rssi):
        """🆕 Stage 2.2 第3步：处理ROUTE_UPDATE消息"""
        try:
            self.log(f"🔄 处理ROUTE_UPDATE来自 {sender_id}")

            # 1. 验证发送者是邻居
            if sender_id not in self.neighbors:
                self.log(f"⚠️  {sender_id} 不是邻居，忽略路由更新")
                return
            
            # 🎯 关键修改：检查双向性
            neighbor_info = self.neighbors[sender_id]
            is_bidirectional = neighbor_info.get('bidirectional', False)
            if not is_bidirectional:
                self.log(f"🛑  {sender_id} 是单向邻居，忽略其路由更新")
                return
            
            # 只有双向邻居才继续处理...
            # 检查对方是否知道我的存在
            received_routes = message.get('routes', {})
            if str(self.node_id) in received_routes:
                # 对方的路由表中包含我 → 对方能收到我的信号
                if sender_id in self.neighbors:
                    self.neighbors[sender_id]['bidirectional_evidence'] = time.time()
                    self.log(f"✅ 双向证据更新: {sender_id} 知道我的存在")
            
            # 2. 计算到该邻居的链路质量
            link_quality = calculate_link_quality(rssi)

            # 3. 处理每条路由
            received_routes = message.get('routes', {})
            updated_count = 0

            for dest_node, route_info in received_routes.items():
                dest_node = int(dest_node)

                # 是否双向邻居
                is_bidirectional_nbs = dest_node in message.get('bi_nbs')

                # 传递跳数参数
                reported_hops = route_info.get('h', 1)
            
                # 跳过无效目标
                if self._should_skip_route_learning(dest_node, sender_id, reported_hops):
                    continue

                # 提取邻居报告的信息
                reported_metric = route_info.get('m', 0.5)
                reported_seq = route_info.get('s', 0)

                # 🎯 距离矢量算法
                total_metric = reported_metric * link_quality
                total_hops = reported_hops + 1

                # 更新路由表
                updated = self.routing_table.update_route(
                    dest=dest_node,
                    next_hop=sender_id,
                    metric=total_metric,
                    hop_count=total_hops,
                    seq_num=reported_seq,
                    is_bidirectional = is_bidirectional_nbs
                )

                if updated:
                    updated_count += 1
                    self.log(f"   路由学习: 到 {dest_node} 通过 {sender_id}, "
                            f"质量 {total_metric:.3f}, 跳数 {total_hops}")
                    
            if updated_count > 0:
                self.log(f"✅ 从 {sender_id} 更新了 {updated_count} 条路由")
            else:
                self.log(f"ℹ️  从 {sender_id} 未学到新路由")

        except Exception as e:
            self.log(f"❌ ROUTE_UPDATE处理错误: {e}", 'error')
            import traceback
            self.log(traceback.format_exc(), 'error')

    def _should_skip_route_learning(self, dest_node, sender_id, reported_hops):
        """判断是否应该跳过路由学习"""
        # 0. 最大跳数检查
        if reported_hops >= self.MAX_HOP_COUNT:
            self.log(f"    跳过学习: 到{dest_node}的跳数{reported_hops}超过最大限制{self.MAX_HOP_COUNT}")
            return True

        # 1. 无效目标
        if not dest_node:
            return True
        
        # 2. 目标是自己
        if dest_node == self.node_id:
            return True
        
        # 3. 目标是发送者本身（这是直接路由，不应该学）
        if dest_node == sender_id:
            return True
        
        # 4. 下一跳不可达（发送者不是邻居）
        if sender_id not in self.neighbors:
            return True
        
        # 5. 目标已经是直接邻居（保持直接路由）
        if dest_node in self.neighbors:
            return True
        
        # 6. 🎯 新增：水平分割检查（防止路由循环）
        # 获取我当前到dest的路由
        current_route = self.routing_table.get_best_route(dest_node)
        if current_route:
            current_hops = current_route['hop_count']

            # 情况1：如果新路由的跳数 >= 当前跳数 + 1
            # 说明这个路由可能经过我，或者是循环路由
            if reported_hops >= current_hops + 1:
                self.log(f"    跳过学习: 到{dest_node}的新路由跳数{reported_hops} >= 当前{current_hops}+1")
                return True
            
            # 情况2：毒性逆转检查
            # 检查我是否在sender到dest的路径上
            # 如果sender报告的路由跳数很大，可能经过了我和sender之间的循环
            if reported_hops > 2 and current_hops == 1:
                # 如果我是直接邻居，但sender报告的跳数很大，可能有问题
                route_to_sender = self.routing_table.get_best_route(sender_id)
                if route_to_sender and route_to_sender['hop_count'] == 1:
                    # sender是我的直接邻居，但他报告的路由跳数很大
                    # 这可能是我已经告诉他的路由，不应该再学回来
                    self.log(f"    跳过学习: 可能的路由循环 {sender_id}->{dest_node}")
                    return True

        return False

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
                # 🆕 新增：双向证据字段（初始为None）
                'bidirectional_evidence': current_time if is_bidirectional else None,
                'stability': stability
            }
            
            # 更新路由表
            self.routing_table.update_route(
                dest=neighbor_id,
                next_hop=neighbor_id,
                metric=route_metric,
                hop_count=1,
                is_bidirectional=is_bidirectional #1213 added
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
                hop_count=1,
                is_bidirectional=is_bidirectional_now # 1213 added
            )

            # 🆕 记录状态变化
            if is_bidirectional_now and not was_bidirectional:
                self.log(f"🔄 邻居 {neighbor_id} 升级为双向连接")
            elif not is_bidirectional_now and was_bidirectional:
                self.log(f"⚠️ 邻居 {neighbor_id} 降级为单向连接")
                
            info_msg = f"🔄 更新邻居: {neighbor_id}, RSSI: {avg_rssi:.1f}dBm, 度量: {route_metric:.3f}, {'双向' if is_bidirectional_now else '单向'}"
            self.log(info_msg)
    
    def _check_bidirectional(self, neighbor_id, rssi):
        """🆕 改进：基于证据的双向链路检测"""
        if neighbor_id not in self.neighbors:
            return False
        
        neighbor = self.neighbors[neighbor_id]
        current_time = time.time()

        # 1. 基础信号强度检查
        if rssi < -110:  # 信号太弱
            return False
        
        # 2. 检查是否有有效的双向证据
        if 'bidirectional_evidence' in neighbor and neighbor['bidirectional_evidence'] is not None:
            evidence_age = current_time - neighbor['bidirectional_evidence']
            
            # 证据有效期：300秒（5分钟）
            if evidence_age < 300:
                return True
            else:
                # 证据过期，清空
                neighbor['bidirectional_evidence'] = None

        # 3. 没有有效证据，尝试获取
        # （这里可以调用主动验证方法，暂时先基于RSSI判断）
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
            return {'next_hop': self.node_id, 'metric': 1.0, 'hop_count': 0, 'is_bidirectional': True}
        
        # 获取路由
        route = self.routing_table.get_best_route(dest)
        if not route:
            return None
        
        # 🎯 检查是否是双向路由
        if not route.get('is_bidirectional', True):  # 默认假设是双向
            self.log(f"⚠️  到{dest}的路由不是双向的，寻找替代路径")
            # 尝试寻找替代的双向路由
            return self._find_alternative_bidirectional_route(dest)
        
        return route
    
    def _find_alternative_bidirectional_route(self, dest):
        """简化版：寻找替代双向路由"""
        # 方法1：直接返回质量最好的双向邻居作为下一跳
        best_bidirectional_neighbor = None
        best_metric = 0
        
        for nid, info in self.neighbors.items():
            if info.get('bidirectional', False):
                metric = info.get('route_metric', 0)
                if metric > best_metric:
                    best_metric = metric
                    best_bidirectional_neighbor = nid
        
        if best_bidirectional_neighbor:
            # 假设这个邻居有到目标的路由
            return {
                'next_hop': best_bidirectional_neighbor,
                'metric': best_metric * 0.8,  # 转发惩罚
                'hop_count': 2,  # 假设是2跳
                'is_bidirectional': True,
                'assumed': True  # 标记为假设路由
            }
        
        return None

    def _handle_hello(self, sender_id, message, rssi):
        """处理HELLO消息 - 增强：包含RSSI信息"""
        # 🆕 新增：检查HELLO消息中是否提到我
        kn_nbs = message.get('kn_nbs', [])
        if isinstance(kn_nbs, list) and self.node_id in kn_nbs:
            # 对方在HELLO中提到了我
            if sender_id in self.neighbors:
                self.neighbors[sender_id]['bidirectional_evidence'] = time.time()
                self.log(f"✅ HELLO确认双向: {sender_id} 在HELLO中提到了我")

        # 邻居信息已在 _update_neighbor 中更新
        neighbors_list = list(self.neighbors.keys())
        self.log(f"   当前邻居: {neighbors_list}")
    
    def _handle_ping(self, sender_id, message, rssi):
        """处理PING消息 - 增强：支持路由转发"""
        target_id = message.get('target')

        # 1. 如果PING的目标是自己，直接回复PONG
        if target_id == self.node_id:
            info_msg = f"✅ 响应PING来自 {sender_id}, RSSI: {rssi}dBm"
            self.log(info_msg)
            self.send_pong(sender_id, message.get('seq'), message)
            return

        # 2. 如果PING的目标不是自己，检查是否有到目标的路由
        info_msg = f"📨 收到PING来自 {sender_id} (目标: {target_id}), RSSI: {rssi}dBm"
        self.log(info_msg)

        # 3. 检查是否可以转发
        if self._can_forward_ping(message, sender_id, target_id):
            self._forward_ping(message, sender_id, target_id)
        else:
            warn_msg = f"⚠️ 无法转发PING到 {target_id}，无可用路由"
            self.log(warn_msg, 'warning')

    def _can_forward_ping(self, message, sender_id, target_id):
        """检查是否可以转发PING消息"""
        # 1. 防止无限循环：检查消息是否已经经过本节点
        if 'path' in message:
            path = message.get('path', [])
            if self.node_id in path:
                self.log(f"🔄 检测到循环PING，已处理过此消息")
                return False
            
        # 2. 检查TTL（生存时间）
        ttl = message.get('ttl', 3)
        if ttl <= 0:
            self.log(f"⏱️  PING TTL耗尽，丢弃")
            return False
        
        # 3. 检查是否有到目标的路由
        if not self.routing_table.get_best_route(target_id):
            self.log(f"❌ 无到目标 {target_id} 的路由")
            return False
        
        # 4. 下一跳不是发送者（防止回传）
        route = self.routing_table.get_best_route(target_id)
        next_hop = route['next_hop']
        if next_hop == sender_id:
            self.log(f"⚠️  下一跳 {next_hop} 是发送者，可能形成循环")
            return False
        
        return True
    
    def _forward_ping(self, original_message, sender_id, target_id):
        """转发PING消息"""
        try:
            # 1. 获取到目标的最佳路由
            route = self.routing_table.get_best_route(target_id)
            if not route:
                return False
            
            next_hop = route['next_hop']
            hop_count = route['hop_count']

            # 2. 准备转发消息
            forward_message = original_message.copy()

            # 3. 更新路径记录（防止循环）
            if 'path' not in forward_message:
                forward_message['path'] = []
            forward_message['path'].append(self.node_id)

            # 5. 减少TTL
            forward_message['ttl'] = forward_message.get('ttl', 3) - 1

            # 6. 设置转发时间戳
            forward_message['forward_ts'] = time.time()

            # 7. 发送转发的PING
            success = self._send_via_lora(forward_message, target_id=next_hop)

            if success:
                log_msg = f"📤 转发PING: {sender_id}→{target_id} (通过{next_hop}, 跳数{hop_count}, TTL={forward_message['ttl']})"
                self.log(log_msg)
                return True
            else:
                self.log(f"❌ PING转发失败到 {next_hop}")
                return False
        
        except Exception as e:
            self.log(f"❌ 转发PING错误: {e}", 'error')
            return False

    def _handle_pong(self, sender_id, message, rssi):
        """处理PONG消息 - 支持路由转发"""
        target_id = message.get('target')
        path = message.get('path', [])

        # 1. 如果PONG的目标是自己
        if target_id == self.node_id:
            info_msg = f"✅ 收到PONG来自 {sender_id}, RSSI: {rssi}dBm"
            self.log(info_msg)

            # 显示路径信息
            if path:
                self.log(f"🛣️  PONG路径: {'→'.join(map(str, path))}")

                # 原始发送者是路径的第一个节点
                if len(path) > 0:
                    original_sender = path[0]
                    self.log(f"🔄 原始发送者: {original_sender}")
            return
        
        # 2. 根据path判断是否需要转发
        if self._should_forward_by_path(path):
            self._forward_pong(message, sender_id, target_id)
        else:
            info_msg = f"📨 收到PONG来自 {sender_id} (目标: {target_id}), 忽略"
            self.log(info_msg)

    def _should_forward_by_path(self, path):
        """根据路径判断是否需要转发"""
        if not path:
            return False
        
        if self.node_id not in path:
            return False
        
        # 找到本节点在路径中的位置
        try:
            my_index = path.index(self.node_id)
        except ValueError:
            return False
        
        # 如果本节点是路径的最后一个，不应该转发（已经是最后一跳）
        if my_index == len(path) - 1:
            return False
        
        # 本节点在路径中间，需要转发
        return True

    def _forward_pong(self, original_message, sender_id, target_id):
        """转发PONG消息"""
        try:
            # 1. 获取原路径
            path = original_message.get('path', [])
            if not path:
                self.log("⚠️  PONG无路径信息，无法转发")
                return False
            
            # 2. 我是转发者，需要将PONG发回给上一个节点
            # 路径格式: [发起者, 转发者1, 转发者2, ..., 目标]
            # PONG路径应该反向：目标, ..., 转发者2, 转发者1, 发起者

            # 找到我在路径中的位置
            if self.node_id not in path:
                self.log(f"⚠️  本节点 {self.node_id} 不在PONG路径中")
                return False
            
            my_index = path.index(self.node_id)
            if my_index == 0:
                # 我是发起者，不应该转发PONG
                return False
            
            # 3. 上一个节点
            prev_node = path[my_index - 1]

            # 4. 准备转发消息
            forward_message = original_message.copy()
            forward_message['forward_ts'] = time.time()

            # 5. 发送转发的PONG
            success = self._send_via_lora(forward_message, target_id=prev_node)

            if success:
                log_msg = f"📤 转发PONG到 {prev_node} (原目标: {target_id})"
                self.log(log_msg)
                return True
            else:
                self.log(f"❌ PONG转发失败到 {prev_node}")
                return False     
        
        except Exception as e:
            self.log(f"❌ 转发PONG错误: {e}", 'error')
            return False
    
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
            threading.Thread(target=self._route_maintenance_worker, daemon=True)
        ]
        
        for thread in threads:
            thread.start()
        
        self.log(f"🟢 Mesh节点 {self.node_id} 已启动 (Stage 2.2 路由支持)")
    
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

                # 🆕 新增：先清理过期证据
                self._cleanup_expired_evidence()

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
        """路由维护工作线程 - 增强：发送ROUTE_UPDATE"""
        last_route_update = 0

        while self.running:
            try:
                current_time = time.time()

                # 🆕 第2步：定期发送ROUTE_UPDATE
                if current_time - last_route_update > self.route_update_interval:
                    self._send_route_update()
                    last_route_update = current_time

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
    
    def _send_route_update(self):
        """🆕 Stage 2.2 第2步：发送ROUTE_UPDATE消息"""
        # 获取完整路由表摘要
        route_summary = self._get_full_route_summary()
        
        if not route_summary:
            self.log("ℹ️ 无路由可广播，跳过ROUTE_UPDATE")
            return
        
        # 新增：统计双向邻居
        bi_nbs = [] #bi_neighbors
        for nid, info in self.neighbors.items():
            if info.get('bidirectional', False):
                bi_nbs.append(nid)
        if not bi_nbs:
            self.log("ℹ️ 无双向邻居，跳过路由更新")
            return

        message = {
            'type': 'RU',
            'node_id': self.node_id,
            'ts': time.time(),#timestamp
            'routes': route_summary,
            'Nnb': len(self.neighbors),
            'bi_nbs': bi_nbs
        }
        
        self._send_via_lora(message)
        self.log(f"📤 向{len(bi_nbs)}个双向邻居发送ROUTE_UPDATE")

    def _get_full_route_summary(self):
        """🆕 获取完整路由摘要"""
        summary = {}
        
        # 从路由表获取所有路由
        all_routes = self.routing_table.get_all_routes()
        
        for dest, route in all_routes.items():
            if dest == self.node_id:
                continue  # 不广播到自己的路由
            
            if route['hop_count'] <= self.MAX_HOP_COUNT:
                summary[dest] = {
                    'm': round(route['metric'], 3),
                    'h': route['hop_count'],
                    's': route.get('seq', 0)
                }
            else:
                self.log(f"⚠️  跳过广播到{dest}的路由: 跳数{route['hop_count']}超过限制")
        
        return summary

    def send_hello(self, seq=0):
        """发送HELLO消息"""
        # 🆕 获取我已知的邻居
        kn_nbs = list(self.neighbors.keys())
        
        # 🆕 获取确认的双向邻居
        bi_nbs = []
        for nid in kn_nbs:
            if nid in self.neighbors:
                if self._check_bidirectional(nid, self.neighbors[nid].get('rssi', -120)):
                    bi_nbs.append(nid)

        message = {
            'type': 'HELLO',
            'node_id': self.node_id,
            'ts': time.time(),
            'seq': seq,
            'kn_nbs': kn_nbs[:10],  # 最多包含10个邻居
            'bi_nbs': bi_nbs[:5]  # 最多5个双向邻居
        }
        self._send_via_lora(message)  # 广播，不指定target_id
    
    def send_ping(self, target_id):
        """发送PING消息 - 支持路由转发"""
        # 1. 如果是邻居，直接发送
        if target_id in self.neighbors:
            return self._send_direct_ping(target_id)
        
        # 2. 如果不是邻居，检查路由
        route = self.routing_table.get_best_route(target_id)
        if not route:
            warn_msg = f"⚠️ 无到目标 {target_id} 的路由"
            self.log(warn_msg, 'warning')
            return False
        
        # 3. 通过路由发送
        next_hop = route['next_hop']
        hop_count = route['hop_count']

        message = {
            'type': 'PING',
            'node_id': self.node_id,
            'target': target_id,
            'ts': time.time(),
            'seq': int(time.time()),
            # 🆕 新增转发相关字段
            'ttl': hop_count + 2,  # TTL = 跳数 + 2（预留余量）
            'path': [self.node_id],  # 路径记录
            'hop_count': hop_count,  # 预估跳数
            'is_routed': True  # 标记为路由PING
        }

        success = self._send_via_lora(message, target_id=next_hop)

        if success:
            log_msg = f"📤 发送路由PING到 {target_id} (通过{next_hop}, 跳数{hop_count})"
            self.log(log_msg)
            return True
        else:
            return False
        
    def _send_direct_ping(self, target_id):
        """发送直接PING（给邻居）"""
        message = {
            'type': 'PING',
            'node_id': self.node_id,
            'target': target_id,
            'ts': time.time(),
            'seq': int(time.time()),
            'is_direct': True  # 标记为直接PING
        }
        
        success = self._send_via_lora(message, target_id=target_id)
        return success
    
    def send_pong(self, target_id, in_reply_to, original_message=None):
        """发送PONG响应 - 支持路由"""
         # 检查是否需要路由
        if target_id in self.neighbors:
            # 直接邻居，直接回复
            return self._send_direct_pong(target_id, in_reply_to)
        else:
            # 需要通过路由回复
            return self._send_routed_pong(target_id, in_reply_to, original_message)
        
    def _send_direct_pong(self, target_id, in_reply_to):
        """发送直接PONG"""
        message = {
            'type': 'PONG',
            'node_id': self.node_id,
            'target': target_id,
            'ts': time.time(),
            'in_reply_to': in_reply_to,
            'is_direct': True
        }
        
        success = self._send_via_lora(message, target_id=target_id)
        return success
    
    def _send_routed_pong(self, target_id, in_reply_to, original_message=None):
        """发送需要路由的PONG"""
        # 查找路由
        route = self.routing_table.get_best_route(target_id)
        if not route:
            self.log(f"❌ 无到 {target_id} 的路由，无法发送PONG")
            return False
        
        next_hop = route['next_hop']
        
        message = {
            'type': 'PONG',
            'node_id': self.node_id,
            'target': target_id,
            'ts': time.time(),
            'in_reply_to': in_reply_to,
            # 🆕 路由相关字段
            'original_sender': self.node_id,
            'path': [self.node_id],  # PONG的路径
            'is_routed': True
        }
        
        # 如果有关联的PING消息，添加路径信息
        if original_message and 'path' in original_message:
            message['path'] = original_message['path'] + [self.node_id]
        
        success = self._send_via_lora(message, target_id=next_hop)
        
        if success:
            self.log(f"📤 发送路由PONG到 {target_id} (通过{next_hop})")
        
        return success
    
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
            'Nnb': len(self.neighbors),
            # 🆕 新增路由信息
            'routes': route_details,
            'route_count': len(route_details),
            'reachable_nodes': self.routing_table.get_reachable_nodes(),
            'route_statistics': route_stats,
            'running': self.running
        }
    
    def _cleanup_expired_evidence(self):
        """清理过期的双向证据"""
        current_time = time.time()
        
        for neighbor_id, info in self.neighbors.items():
            if 'bidirectional_evidence' in info and info['bidirectional_evidence'] is not None:
                evidence_age = current_time - info['bidirectional_evidence']
                
                # 证据过期（超过5分钟）
                if evidence_age > 300:
                    info['bidirectional_evidence'] = None
                    info['bidirectional'] = False  # 更新状态
                    self.log(f"🗑️ 双向证据过期: 邻居 {neighbor_id}")

    def print_status(self):
        """🔧 增强：打印状态，显示RSSI和路由信息"""
        status = self.get_status()
        status_msg = f"\n=== Mesh节点 {self.node_id} ==="
        status_msg += f"\n状态: {'🟢 运行中' if status['running'] else '🔴 已停止'}"
        status_msg += f"\n邻居数量: {status['Nnb']}个"
        status_msg += f"\n路由数量: {status['route_count']}个"
        
        if status['neighbor_details']:
            status_msg += "\n邻居详情:"
            for nid, details in status['neighbor_details'].items():
                link_type = "🟢" if details['bidirectional'] else "🟡"
                status_msg += f"\n  {link_type} {nid}: RSSI={details['rssi']:.1f}dBm, 年龄={details['age']}s, 质量={details['link_quality']:.2f}, 稳定={details['stability']:.2f}, 度量={details['route_metric']:.3f}, 双向性={details['bidirectional']}"
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