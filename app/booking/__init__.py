"""订舱业务核心：产出 BookingRecord；扁平三件套由其投影。"""

from app.booking.process import process_booking, triple_from_record

__all__ = ["process_booking", "triple_from_record"]
# feedback 子模块：from app.booking.feedback import ...
