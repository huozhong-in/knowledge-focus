import datetime
import pytz



# 取得当前时间的timestamp
def get_current_timestamp():
    return int(datetime.datetime.now().timestamp())

# 取得当前时间的UTC时间字符串
def get_current_utc_time_str():
    return datetime.datetime.now(pytz.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

