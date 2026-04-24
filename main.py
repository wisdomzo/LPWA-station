# [file name]: main.py (更新版本)
# [file content begin]
#!/usr/bin/env python3
"""
主菜单程序 - 集成Mesh网络功能
"""

# 导入Mesh网络功能
from network_manager import MeshNetworkManager

def main():
    """主函数"""
    mesh_manager = MeshNetworkManager()
    
    while True:
        print("\n" + "="*50)
        print("           树莓派5 Station系统")
        print("="*50)
        print("1. GNSS位置信息")
        print("2. UPS电源信息") 
        print("3. LoRa 920MHz控制")
        print("4. LoRa 429MHz控制")
        print("5. 双LoRa并行控制")
        print("6. Mesh网络系统")
        print("7. DR-IoT追加GNSS信息")
        print("0. 退出程序")
        print("="*50)
        
        try:
            choice = input("请选择功能: ").strip()
            
            if choice == '1':
                mesh_manager.show_gnss_info()
            elif choice == '2':
                mesh_manager.show_ups_info()
            elif choice == '3':
                mesh_manager.start_lora_920()
            elif choice == '4':
                mesh_manager.start_lora_429()
            elif choice == '5':
                mesh_manager.start_dual_lora()
            elif choice == '6':
                print("还没做。")
            elif choice == '7':
                mesh_manager.driot_add_gnss_info()
            elif choice == '0':
                print("再见！")
                break
            else:
                print("❌ 无效选择，请重新输入")
                
        except KeyboardInterrupt:
            print("\n\n再见！")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")

if __name__ == "__main__":
    main()
# [file content end]