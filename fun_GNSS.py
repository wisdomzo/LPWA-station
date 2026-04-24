#!/usr/bin/env python3

from gps3 import agps3
import coordTransform_py.coordTransform_utils as transform 
import time
import json
from datetime import datetime, timezone, timedelta




def get_gnss_location(timeout = 1): 
    #GPSDSocket creates a GPSD socket connection & request/retrieve GPSD output.
    gps_socket = agps3.GPSDSocket()
    #DataStream unpacks the streamed gpsd data into python dictionaries.
    data_stream = agps3.DataStream()
    gps_socket.connect()
    gps_socket.watch()

    start_time = time.time()   # 记录开始时间

    gcj02_lng_lat = [0.0,0.0]
    bd09_lng_lat = [0.0,0.0]

    # print('gps device make wgs84 coordinate\r\ngcj02 coordinate is for amap or google map\r\nbd09 coordinate is for baidu map\r\n\033[1;31m Please press Ctrl+c if want to exit \033[0m')
    for new_data in gps_socket:

        # 超时判断
        if time.time() - start_time > timeout:
            return None   # 超时直接返回 None
        
        if new_data:
            # 先检查数据包类型
            try:
                data_dict = json.loads(new_data)
                if data_dict.get('class') == 'TPV':
                    data_stream.unpack(new_data)
                    if data_stream.lat != 'n/a' and data_stream.lon != 'n/a':
                        # 处理位置数据
                        gcj02_lng_lat = transform.wgs84_to_gcj02(float(data_stream.lon),float(data_stream.lat))
                        bd09_lng_lat = transform.wgs84_to_bd09(float(data_stream.lon),float(data_stream.lat))
                        
                        #print('altitude       = ', data_stream.alt,'M')
                        #print('wgs84 lon,lat  = ',data_stream.lon,',',data_stream.lat)
                        #print('google lon.lat = %.9f,%.9f' %(gcj02_lng_lat[1],gcj02_lng_lat[0]))
                        #print('amap lon.lat   = %.9f,%.9f' %(gcj02_lng_lat[0],gcj02_lng_lat[1]))
                        #print('bd09 lon,lat   = %.9f,%.9f' %(bd09_lng_lat[0],bd09_lng_lat[1]))
                        #print('speed          = ', data_stream.speed,'KM/H')

                        outputDict = {
                            #'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                            'GNSS_time': convert_gnss_time(data_stream.time, target_tz_hours=9).strftime("%Y-%m-%d %H:%M:%S"),
                            'altitude': data_stream.alt,
                            #'wgs84_lon': data_stream.lon,
                            #'wgs84_lat': data_stream.lat,
                            'google_lon': gcj02_lng_lat[1],
                            'google_lat': gcj02_lng_lat[0],
                            #'amap_lon': gcj02_lng_lat[0],
                            #'amap_lat': gcj02_lng_lat[1],
                            #'bd09_lon': bd09_lng_lat[0],
                            #'bd09_lat': bd09_lng_lat[1],
                            'speed': data_stream.speed,
                            #'mode': data_stream.mode,
                        }
                        return outputDict
                else:
                    # 忽略非TPV数据包
                    continue
                    
            except json.JSONDecodeError:
                continue
    return None


def convert_gnss_time(gnss_time_str, target_tz_hours=8):
    """
    将GNSS UTC时间转换为指定时区
    target_tz_hours: 目标时区偏移（小时），如北京+8，纽约-5
    """
    # 解析GNSS时间
    gnss_time = datetime.fromisoformat(gnss_time_str.replace('Z', '+00:00'))
    
    # 创建目标时区
    target_tz = timezone(timedelta(hours=target_tz_hours))
    
    # 转换时区
    local_time = gnss_time.astimezone(target_tz)
    
    return local_time



#if __name__ == "__main__":
#    get_gnss_location()