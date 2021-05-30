# standard library imports
import hmac
import hashlib
from enum import Enum
from functools import wraps
from http import HTTPStatus

# pip imports
from werkzeug.security import safe_str_cmp
from flask import Response, jsonify, request, abort

# local imports
from app import config

def create_hmac_hexdigest(hmac_data: str, secret_key: str = None) -> str:
    """Creates HMAC hexdigest using the hmac_data and returns it."""
    hmac_hash = hmac.new(
        secret_key.encode('utf-8'),
        hmac_data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return hmac_hash

def is_valid_digest(hash_a: str, hash_b: str) -> bool:
    """Compares two hashes using `hmac.compare_digest`."""
    return hmac.compare_digest(hash_a, hash_b)

def response(status_code: int = HTTPStatus.OK, status: str = HTTPStatus.OK.phrase, **kwargs) -> Response:
    """Wrapper for `flask.jsonify`

    :param int status_code: HTTP status code, defaults to `200`
    :param str status: HTTP status message or your own custom status, defaults to `OK`
    :param **kwargs: Arbitrary keyword arguments, these will be added to the returned `Response` as JSON key/value pairs
    :return flask.jsonify (flask.Response)
    """
    resp = jsonify(status_code=status_code, status=status, **kwargs)
    resp.status_code = status_code
    return resp

def auth_required(f):
    """Check HTTP `Authorization` header against the value of `config.UPLOAD_PASSWORD`, calls `flask.abort` if the password does not match."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if config.UPLOAD_PASSWORD:
            authorization_header = request.headers.get('Authorization')
            if authorization_header is None or safe_str_cmp(config.UPLOAD_PASSWORD, authorization_header) is False:
                abort(HTTPStatus.UNAUTHORIZED)
        return f(*args, **kwargs)
    return decorated_function

class Message(str, Enum):
    # Services
    INVALID_FILE = 'Invalid file'
    INVALID_FILE_TYPE = 'Invalid file type'
    FILE_DELETED = 'This file has been deleted, you can now close this page'

    INVALID_URL = 'Invalid URL'
    URL_DELETED = 'This short URL has been deleted, you can now close this page'

    # Embeds
    URL = 'URL'
    DELETION_URL = 'Deletion URL'
    CLICK_HERE_TO_VIEW = 'Click here to view'
    CLICK_HERE_TO_DELETE = 'Click here to delete'

    FILE_UPLOADED = 'New file has been uploaded!'
    URL_SHORTENED = 'URL has been shortened!'