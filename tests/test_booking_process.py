from app.booking import process_booking, triple_from_record
from app.models import BookingRecord


def test_process_booking_returns_record():
    record = process_booking(file_path="data/samples/BKG.pdf")
    assert isinstance(record, BookingRecord)
    assert record.raw_extracted_data is not None
    assert record.validated_data is not None
    assert record.validation_report is not None
    assert record.history
    assert record.validated_data.get("vessel") == "MSC"


def test_triple_projected_from_record():
    record = process_booking(file_path="data/samples/BKG.pdf")
    flat = triple_from_record(record)
    assert flat["validated_data"] == record.validated_data
    assert flat["raw_extracted_data"] == record.raw_extracted_data
    assert flat["validation_report"]["overall"] == record.validation_report.overall
