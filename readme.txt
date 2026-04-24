0 更新说明
时间：11/21/2025
版本：0.1
更新说明：
# 实现了GNSS数据的获取
# 实现了UPS关联数据的读取

1 关于UPS（https://www.waveshare.net/wiki/UPS_HAT_(E)）

1.1 开启I2C接口
sudo raspi-config 
选择 Interfacing Options -> I2C ->yes 启动 i2C 内核驱动
sudo reboot

1.2 电池电量检测
sudo apt-get install python3-smbus
wget https://files.waveshare.com/wiki/UPS-HAT-E/UPS_HAT_E.zip
unzip UPS_HAT_E.zip
cd UPS_HAT_E
python3 ups.py

1.3 电池电量图标显示
cd ~/UPS_HAT_E
DISPLAY=':0.0' python3 batteryTray.py
如果没有效果测试测试如下：
cd ~/UPS_HAT_E
sudo chmod +x main.sh  #给脚本赋予运行权限
./main.sh   #千万不要加sudo 
sudo reboot

1.4 树莓派5解除电流限制
sudo rpi-eeprom-config --edit
添加以下设置可以解除3A电流限制，提供5A电流。
PSU_MAX_CURRENT=5000


2 关于GNSS（https://www.waveshare.net/wiki/MAX-M8Q_GNSS_HAT）

2.1 开启UART接口
sudo raspi-config
#选择Interfacing Options -> Serial，关闭shell访问，打开硬件串口
sudo reboot

2.2 安装软件与修改参数
2.2.1 安装Python函数库
sudo apt-get update
sudo apt-get install gpsd gpsd-clients 
sudo pip3 install gps3
2.2.2 修改gpsd参数
打开gpsd文档
sudo nano /etc/default/gpsd
将文档以下参数修改后保存退出
# Start the gpsd daemon automatically at boot time
START_DAEMON="true"
# Use USB hotplugging to add new USB devices automatically to the daemon
USBAUTO="false"
# Devices gpsd should collect to at boot time.
# They need to be read/writable, either by user gpsd or the group dialout.
DEVICES="/dev/ttyAMA0"
# Other options you want to pass to gpsd
GPSD_OPTIONS="-n"
2.2.3 下载源码
mkdir ~/Documents/MAX-XXX_GNSS_HAT_Code
cd ~/Documents/MAX-XXX_GNSS_HAT_Code/
wget https://www.waveshare.net/w/upload/0/0f/MAX-XXX_GNSS_HAT_Code.zip
unzip MAX-XXX_GNSS_HAT_Code.zip


3 开放多个ttyAMA
树莓派5: sudo nano /boot/firmware/config.txt
# 启用主UART
enable_uart=1
# 启用额外UART（按顺序）
dtoverlay=uart0
dtoverlay=uart1  
dtoverlay=uart2
dtoverlay=uart3
dtoverlay=uart4

4 开机时间同步（internet or GNSS）
auto_time_daemon.py
fun_GNSS.py
步骤：
・将【auto_time_daemon.py】和【fun_GNSS.py】拷贝到station目录
・sudo nano /etc/systemd/system/auto_time_daemon.service
=======
[Unit]
Description=Auto Time Sync Daemon (Internet or GNSS)
After=network.target gpsd.service

[Service]
Type=simple
WorkingDirectory=/home/用户名/Documents/station
ExecStart=/home/用户名/Documents/station/venv/bin/python /home/用户名/Documents/station/auto_time_daemon.py
Restart=on-failure
RestartSec=5s

# 可选：设置环境变量
Environment="PYTHONPATH=/home/用户名/Documents/station"
Environment="PATH=/home/用户名/Documents/station/venv/bin:/usr/bin"

[Install]
WantedBy=multi-user.target
========
・sudo systemctl daemon-reload
・sudo systemctl restart auto_time_daemon.service
・sudo systemctl enable auto_time_daemon.service 





开发文档更新：

Stage 1：基础Mesh网络实现
1. 基础网络架构
* 节点初始化与唯一标识（node_id）
* LoRa模块集成与配置管理
* 基本的启动/停止控制

2. 邻居发现机制
* HELLO消息广播（周期性60秒）
* 邻居表维护（基于last_seen时间戳）
* 邻居超时清理（180秒）

3. 基础通信协议
* PING/PONG消息机制（双向验证）
* 广播消息处理
* 基本的消息路由（仅直接邻居）

4 网络监控
* 实时状态显示（s命令）
* 邻居列表查看
* 基础日志系统

Stage 2.1：增强路由功能
1. 完整的路由表系统
* 路由增删改查（update_route, remove_route）
* 序列号管理（防环路，修复了递增问题）
* 路由超时机制（直接邻居180s，多跳路由300s）
* 路由统计和分析（get_route_statistics）
* 路由表打印和监控（print_routing_table）

2. 链路质量评估体系
* calculate_link_quality(rssi)      # RSSI转质量分（0-1）
* calculate_route_metric()          # 综合路由度量计算
* _calculate_stability()            # 连接稳定性评估
* RSSI滑动窗口统计（10个样本）

3. 智能路由功能
* get_intelligent_route(dest)       # 优选高质量双向路径
* 双向链路检测框架（简化版，基于RSSI阈值）
* get_best_neighbor()              # 最佳邻居选择
* 路由维护线程（定期清理和更新）

4. 消息传输优化
* 单播/广播分离（目标地址0xFFFF vs 具体节点）
* 改进的消息处理回调
* 增强的错误处理和日志

5. 监控和调试增强
* 详细状态显示（s命令 - 包含RSSI、质量、稳定性）
* 路由表查看（r命令）
* 路由统计（rstats命令）
* 统一日志系统（文件+控制台）
* 智能路由测试（route命令）