from __future__ import annotations


def parse_error_logs(log_lines: list[str]) -> dict:
    errors = [line for line in log_lines if "ERROR" in line]
    return {"error_count": len(errors), "sample_errors": errors[:5]}


def should_alert(error_count: int, threshold: int = 5) -> bool:
    return error_count >= threshold
