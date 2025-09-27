import datetime
import pytz
from pydantic_ai import RunContext
"""
The pytz library in Python provides access to the Olson time zone database, enabling accurate and cross-platform timezone calculations. To obtain a list of timezones available within pytz, you can utilize the following attributes: 

• pytz.all_timezones: This attribute provides an exhaustive list of all timezone names recognized by pytz, including historical and deprecated zones. It is a sequence of strings, alphabetically sorted. 

    import pytz
    all_zones = pytz.all_timezones
    print(all_zones)

• pytz.common_timezones: This attribute offers a more curated list of commonly used, current timezones. It excludes most deprecated or historical zones, focusing on those likely to be relevant in modern applications. It is also a sequence of strings, alphabetically sorted. 

    import pytz
    common_zones = pytz.common_timezones
    print(common_zones)

Both all_timezones and common_timezones are also available as sets (pytz.all_timezones_set and pytz.common_timezones_set) if set operations are preferred for tasks like checking membership. 
Additionally, pytz allows you to retrieve timezones specific to a country using the pytz.country_timezones() function, which requires an ISO-3166 two-letter country code as an argument. 

import pytz
us_timezones = pytz.country_timezones('US')
print(us_timezones)
"""


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
