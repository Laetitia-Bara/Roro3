"""Journal local sobre, avec un filtre supplémentaire de confidentialité."""

import logging
import re


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        message = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[EMAIL MASQUÉ]", message)
        message = re.sub(r"\b\d{7,}:[A-Za-z0-9_-]{20,}\b", "[TOKEN MASQUÉ]", message)
        return re.sub(
            r"(?i)\b(token|password|secret|authorization|cookie)\s*[:=]\s*\S+",
            r"\1=[MASQUÉ]",
            message,
        )


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(levelname)s %(name)s — %(message)s"))
    logger = logging.getLogger("roro3")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
