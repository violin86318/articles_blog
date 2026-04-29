import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

class Config:
    # 飞书应用配置
    FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
    
    # 多维表格配置
    BASE_ID = os.environ.get("BASE_ID", "")
    TABLE_ID = os.environ.get("TABLE_ID", "")
    VIEW_ID = os.environ.get("VIEW_ID", "")
    USE_LARK_CLI = os.environ.get("USE_LARK_CLI", "")
