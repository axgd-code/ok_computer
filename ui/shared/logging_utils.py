def log_exception(logger, message, exc):
    try:
        logger.exception('%s: %s', message, exc)
    except Exception:
        pass
