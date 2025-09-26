import datetime
import pytz
from pydantic_ai import RunContext

def get_current_time(ctx: RunContext, timezone: str = "UTC") -> str:
    """
    获取当前时间的字符串表示，格式为 "YYYY-MM-DD HH:MM:SS"
    Args:
        timezone (str): 时区名称，默认为 "UTC"
    Returns:
        str: 当前时间的字符串表示
    """
    try:
        tz = pytz.timezone(timezone)
    except Exception:
        tz = pytz.utc
    return datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
