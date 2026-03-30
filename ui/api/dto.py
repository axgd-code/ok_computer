from flask import jsonify

from shared.errors import AppError


def success(payload, status=200):
    return jsonify(payload), status


def error(message, status=400, code='error'):
    return jsonify({'error': message, 'code': code}), status


def from_exception(exc):
    if isinstance(exc, AppError):
        return error(exc.message, status=exc.status, code=exc.code)
    return error(str(exc), status=500, code='internal_error')
