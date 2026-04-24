import serial
import time
from gpiozero import Device, OutputDevice
from gpiozero.pins.lgpio import LGPIOFactory
import subFun
import fun_GNSS

class sx126x:

    M0 = 22
    M1 = 27
    # if the header is 0xC0, then the LoRa register settings dont lost when it poweroff, and 0xC2 will be lost. 
    # cfg_reg = [0xC0,0x00,0x09,0x00,0x00,0x00,0x62,0x00,0x17,0x43,0x00,0x00]
    cfg_reg = [0xC2,0x00,0x09,0x00,0x00,0x00,0x62,0x00,0x12,0x43,0x00,0x00]
    get_reg = bytes(12)
    rssi = False
    addr = 65535
    serial_n = ""
    addr_temp = 0

    #
    # start frequence of two lora module
    #
    # E22-400T22S           E22-900T22S
    # 410~493MHz      or    850~930MHz
    start_freq = 850

    #
    # offset between start and end frequence of two lora module
    #
    # E22-400T22S           E22-900T22S
    # 410~493MHz      or    850~930MHz
    offset_freq = 18

    # power = 22
    # air_speed =2400

    SX126X_UART_BAUDRATE_1200 = 0x00
    SX126X_UART_BAUDRATE_2400 = 0x20
    SX126X_UART_BAUDRATE_4800 = 0x40
    SX126X_UART_BAUDRATE_9600 = 0x60
    SX126X_UART_BAUDRATE_19200 = 0x80
    SX126X_UART_BAUDRATE_38400 = 0xA0
    SX126X_UART_BAUDRATE_57600 = 0xC0
    SX126X_UART_BAUDRATE_115200 = 0xE0

    SX126X_PACKAGE_SIZE_240_BYTE = 0x00
    SX126X_PACKAGE_SIZE_128_BYTE = 0x40
    SX126X_PACKAGE_SIZE_64_BYTE = 0x80
    SX126X_PACKAGE_SIZE_32_BYTE = 0xC0

    SX126X_Power_22dBm = 0x00
    SX126X_Power_17dBm = 0x01
    SX126X_Power_13dBm = 0x02
    SX126X_Power_10dBm = 0x03
    
    baud_rate_dic = {
        1200:SX126X_UART_BAUDRATE_1200,
        2400:SX126X_UART_BAUDRATE_2400,
        4800:SX126X_UART_BAUDRATE_4800,
        9600:SX126X_UART_BAUDRATE_9600,
        19200:SX126X_UART_BAUDRATE_19200,
        38400:SX126X_UART_BAUDRATE_38400,
        57600:SX126X_UART_BAUDRATE_57600,
        115200:SX126X_UART_BAUDRATE_115200
    }

    lora_air_speed_dic = {
        1200:0x01,
        2400:0x02,
        4800:0x03,
        9600:0x04,
        19200:0x05,
        38400:0x06,
        62500:0x07
    }

    lora_power_dic = {
        22:0x00,
        17:0x01,
        13:0x02,
        10:0x03
    }

    lora_buffer_size_dic = {
        240:SX126X_PACKAGE_SIZE_240_BYTE,
        128:SX126X_PACKAGE_SIZE_128_BYTE,
        64:SX126X_PACKAGE_SIZE_64_BYTE,
        32:SX126X_PACKAGE_SIZE_32_BYTE
    }


    def __init__(self,serial_num,freq,addr,power,rssi,air_speed=2400,\
                 net_id=0,buffer_size = 240,crypt=0,\
                 relay=False,lbt=False,wor=False,baud_rate=9600):
        self.rssi = rssi
        self.addr = addr
        self.freq = freq
        self.serial_n = serial_num
        self.power = power
        self.baud_rate = baud_rate

        # 使用 gpiozero + LGPIOFactory 设置GPIO
        Device.pin_factory = LGPIOFactory()
        self.m0_pin = OutputDevice(self.M0)
        self.m1_pin = OutputDevice(self.M1)

        self.m0_pin.off()  # 等价于 GPIO.LOW
        self.m1_pin.on()   # 等价于 GPIO.HIGH

        # 先使用9600写入寄存器，然后使用指定波特率传输
        self.ser = serial.Serial(serial_num, 9600)
        self.ser.flushInput()
        self.set(freq, addr, power, rssi, air_speed, net_id, buffer_size, crypt, relay, lbt, wor, baud_rate)
        self.ser.close()
        time.sleep(0.5)
        self.ser = serial.Serial(serial_num, baud_rate)
        time.sleep(0.5)


    def set(self,freq,addr,power,rssi,air_speed=2400,\
            net_id=0,buffer_size = 240,crypt=0,\
            relay=False,lbt=False,wor=False,baud_rate=9600):
        self.send_to = addr
        self.addr = addr
        # We should pull up the M1 pin when sets the module
        self.m0_pin.off()   # 相当于 GPIO.LOW
        self.m1_pin.on()    # 相当于 GPIO.HIGH
        time.sleep(0.5)

        low_addr = addr & 0xff
        high_addr = addr >> 8 & 0xff
        net_id_temp = net_id & 0xff
        if freq > 850:
            freq_temp = freq - 850
            self.start_freq = 850
            self.offset_freq = freq_temp
        elif freq > 410:
            freq_temp = freq - 410
            self.start_freq  = 410
            self.offset_freq = freq_temp
        
        air_speed_temp = self.lora_air_speed_dic.get(air_speed,None)
        # if air_speed_temp != None

        buffer_size_temp = self.lora_buffer_size_dic.get(buffer_size,None)
        # if air_speed_temp != None:

        power_temp = self.lora_power_dic.get(power,None)
        #if power_temp != None:

        if rssi:
            # enable print rssi value 
            rssi_temp = 0x80
        else:
            # disable print rssi value
            rssi_temp = 0x00

        # get crypt
        l_crypt = crypt & 0xff
        h_crypt = crypt >> 8 & 0xff

        if relay == False:
            self.cfg_reg[3] = high_addr
            self.cfg_reg[4] = low_addr
            self.cfg_reg[5] = net_id_temp
            self.cfg_reg[6] = self.baud_rate_dic.get(baud_rate,None) + air_speed_temp
            # 
            # it will enable to read noise rssi value when add 0x20 as follow
            # 
            self.cfg_reg[7] = buffer_size_temp + power_temp + 0x20
            self.cfg_reg[8] = freq_temp
            #
            # it will output a packet rssi value following received message
            # when enable eighth bit with 06H register(rssi_temp = 0x80)
            #
            self.cfg_reg[9] = 0x43 + rssi_temp
            self.cfg_reg[10] = h_crypt
            self.cfg_reg[11] = l_crypt
        else:
            self.cfg_reg[3] = 0x01
            self.cfg_reg[4] = 0x02
            self.cfg_reg[5] = 0x03
            self.cfg_reg[6] = self.baud_rate_dic.get(baud_rate,None) + air_speed_temp
            # 
            # it will enable to read noise rssi value when add 0x20 as follow
            # 
            self.cfg_reg[7] = buffer_size_temp + power_temp + 0x20
            self.cfg_reg[8] = freq_temp
            #
            # it will output a packet rssi value following received message
            # when enable eighth bit with 06H register(rssi_temp = 0x80)
            #
            self.cfg_reg[9] = 0x03 + rssi_temp
            self.cfg_reg[10] = h_crypt
            self.cfg_reg[11] = l_crypt
        self.ser.flushInput()

        for i in range(2):
            self.ser.write(bytes(self.cfg_reg))
            r_buff = 0
            time.sleep(0.2)
            if self.ser.inWaiting() > 0:
                time.sleep(0.1)
                r_buff = self.ser.read(self.ser.inWaiting())
                if r_buff[0] == 0xC1:
                    pass
                    #print("parameters setting is :",end='')
                    #for i in self.cfg_reg:
                    #    print(hex(i),end=' ')
                    #print('\r\n')
                    #print("parameters return is  :",end='')
                    #for i in r_buff:
                    #    print(hex(i),end=' ')
                    #print('\r\n')
                else:
                    #pass
                    print("parameters setting fail :",r_buff)
                break
            else:
                print("setting fail,setting again")
                self.ser.flushInput()
                time.sleep(0.2)
                print('\x1b[1A',end='\r')
                if i == 1:
                    print("setting fail,Press Esc to Exit and run again")
                    # time.sleep(2)
                    # print('\x1b[1A',end='\r')
        
        self.m0_pin.off()   # 相当于 GPIO.LOW
        self.m1_pin.off()    # 相当于 GPIO.LOW
        time.sleep(0.5)


    def get_settings(self):
        # the pin M1 of lora HAT must be high when enter setting mode and get parameters
        self.m1_pin.on()
        time.sleep(0.5)

        # send command to get setting parameters
        self.ser.write(bytes([0xC1,0x00,0x09]))
        time.sleep(0.5)
        if self.ser.inWaiting() > 0:
            time.sleep(0.1)
            self.get_reg = self.ser.read(self.ser.inWaiting())

        # check the return characters from hat and print the setting parameters
        if self.get_reg[0] == 0xC1 and self.get_reg[2] == 0x09:
            fre_temp = self.get_reg[8]
            addr_temp = self.get_reg[3] + self.get_reg[4]
            air_speed_temp = self.get_reg[6] & 0x0F
            power_temp = self.get_reg[7] & 0x03

            print("读取寄存器中的参数：")
            # 读取频率
            frequency = self.start_freq+fre_temp
            print("Frequence is " + str(frequency) + " MHz.")
            # 读取地址
            print("Node address is " + str(addr_temp) + ".")
            # 读取空中速率
            inv_lora_air_speed_dic = {v: k for k, v in self.lora_air_speed_dic.items()}
            rate = inv_lora_air_speed_dic.get(air_speed_temp, None)
            print("Air speed is " + str(rate) + " bps.")
            # 读取发射功率
            inv_lora_power_dic = {v: k for k, v in self.lora_power_dic.items()}
            powerValue = inv_lora_power_dic.get(power_temp, None)
            print("Power is " + str(powerValue) + " dBm.")
            self.m1_pin.off()
            time.sleep(0.5)
            return frequency, addr_temp, rate, powerValue


    def send(self,data):
        # the data format like as following
        # "node address,frequence,payload"
        # "20,868,Hello World"
        self.m0_pin.off()   # 相当于 GPIO.LOW
        self.m1_pin.off()    # 相当于 GPIO.LOW
        time.sleep(0.5)

        self.ser.write(data)
        # if self.rssi == True:
            # self.get_channel_rssi()
        time.sleep(0.1)


    def receive(self):
        if self.ser.inWaiting() > 0:
            time.sleep(0.5)
            r_buff = self.ser.read(self.ser.inWaiting())

            # print the source and frequency
            source, frequency = subFun.get_source_and_frequency(self, r_buff)
            # print Message
            message = subFun.get_message(r_buff)
            # print the rssi
            rssi_dBm = subFun.get_rssi(self, r_buff)
            
            # 🔄 增强：Mesh回调处理 - 增加更详细的日志
            if hasattr(self, 'mesh_callback') and self.mesh_callback:
                try:
                    # 提取消息数据用于Mesh处理
                    if message:
                        if message.startswith('{') and message.endswith('}'):
                            # 🆕 增强：记录Mesh消息的RSSI信息
                            print(f"📨 收到Mesh消息，源: {source}, RSSI: {rssi_dBm}dBm")
                            # 这是Mesh消息，交给回调处理
                            self.mesh_callback(message, rssi_dBm, source)
                            return  # 🚫 Mesh消息不进入普通流程
                        else:
                            # 🆕 新增：记录非Mesh消息
                            print(f"📨 收到普通消息，源: {source}, RSSI: {rssi_dBm}dBm, 内容: {message}")
                except Exception as e:
                    print(f"Mesh回调错误: {e}")
            
            # print the channel noise power
            # noisePower_dBm = subFun.get_channel_rssi(self)
            # 接收GNSS信息
            gnssInfo = fun_GNSS.get_gnss_location(timeout = 1)
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
            # Record data in CSV
            subFun.save_to_csv('output.csv', source, frequency, message, rssi_dBm, GNSS_time, altitude, lon, lat, speed)


    # 🆕 新增：设置Mesh回调的方法
    def set_mesh_callback(self, callback_func):
        """设置Mesh消息回调函数"""
        self.mesh_callback = callback_func
        print("✅ Mesh回调函数已设置")