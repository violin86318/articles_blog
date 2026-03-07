import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # 飞书应用配置
    FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
    
    # 多维表格配置
    BASE_ID = os.environ.get("BASE_ID", "")
    TABLE_ID = os.environ.get("TABLE_ID", "")
