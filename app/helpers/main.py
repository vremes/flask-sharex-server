# standard library imports
import os
import secrets
import sqlite3
import mimetypes
from urllib.parse import urlparse
from functools import cached_property

# pip imports
from magic import from_buffer
from flask import url_for, current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import safe_join, secure_filename

# local imports
from app import config
from app.helpers.utils import create_hmac_hexdigest
from app.helpers.discord.embeds import FileEmbed, ShortUrlEmbed

class File:
    def __init__(self, file_instance: FileStorage, use_original_filename=True):
        """Class for uploaded files which takes the `werkzeug.datastructures.FileStorage` from `flask.Request.files` as first parameter."""
        if isinstance(file_instance, FileStorage) is False:
            raise InvalidFileException(file_instance)

        self.use_original_filename = use_original_filename

        # Private FileStorage instance
        self.__file = file_instance

    @cached_property
    def filename(self) -> str:
        """Returns random filename."""
        custom_filename = secrets.token_urlsafe(config.FILE_TOKEN_BYTES)

        if self.use_original_filename:
            filename = f'{custom_filename}-{self.original_filename_root[:config.ORIGINAL_FILENAME_LENGTH]}'
        else:
            filename = custom_filename

        return f'{filename}{self.extension}'

    @cached_property
    def extension(self) -> str:
        """Returns extension using `python-magic` and `mimetypes`."""
        file_bytes = self.__file.read(config.MAGIC_BUFFER_BYTES)
        mime = from_buffer(file_bytes, mime=True).lower()

        self.add_custom_mimetypes()

        return mimetypes.guess_extension(mime)

    @cached_property
    def original_filename_root(self):
        """Returns the original filename without extension."""
        sec_filename = secure_filename(self.__file.filename.lower())
        root, ext = os.path.splitext(sec_filename)
        return root

    @cached_property
    def hmac(self) -> str:
        """Returns HMAC digest calculated from filename, `flask.current_app.secret_key` is used as secret."""
        return create_hmac_hexdigest(self.filename, current_app.secret_key)
    
    @cached_property
    def url(self) -> str:
        """Returns file URL using `flask.url_for`."""
        return url_for('main.uploads', filename=self.filename, _external=True)
    
    @cached_property
    def deletion_url(self) -> str:
        """Returns deletion URL using `flask.url_for`."""
        return url_for('api.delete_file', hmac_hash=self.hmac, filename=self.filename, _external=True)

    @staticmethod
    def delete(filename: str) -> bool:
        """Deletes the file from `config.UPLOAD_DIR`, if it exists."""
        file_path = safe_join(config.UPLOAD_DIR, filename)

        if os.path.isfile(file_path) is False:
            return False

        os.remove(file_path)

        return True

    def is_allowed(self) -> bool:
        """Check if file is allowed, based on `config.ALLOWED_EXTENSIONS`."""
        if not config.ALLOWED_EXTENSIONS:
            return True

        return self.extension in config.ALLOWED_EXTENSIONS

    def save(self, save_directory = config.UPLOAD_DIR) -> None:
        """Saves the file to `UPLOAD_DIR`."""
        if os.path.isdir(save_directory) is False:
            os.makedirs(save_directory)

        save_path = safe_join(save_directory, self.filename)

        # Set file descriptor back to beginning of the file so save works correctly
        self.__file.seek(os.SEEK_SET)

        self.__file.save(save_path)

    def add_custom_mimetypes(self):
        """Adds unsupported mimetypes/extensions to `mimetypes` module."""
        mimetypes.add_type('video/x-m4v', '.m4v')

    def embed(self) -> FileEmbed:
        """Returns FileEmbed instance for this file."""
        embed = FileEmbed(
            content_url=self.url, 
            deletion_url=self.deletion_url
        )
        return embed

class InvalidFileException(Exception):
    """Raised when `app.helpers.files.File` is initialized using wrong `file_instance`."""
    def __init__(self, file_instance, *args):
        self.file_instance = file_instance
        super().__init__(*args)

    def __str__(self):
        file_instance_type = type(self.file_instance)
        return f'{self.file_instance} ({file_instance_type}) is not an instance of werkzeug.datastructures.FileStorage ({FileStorage})'

class ShortUrl:
    def __init__(self, url=None):
        self.url = url

        # Database connection
        self.db = self.__get_db()
        self.cursor = self.db.cursor()

    @cached_property
    def token(self) -> str:
        return secrets.token_urlsafe(config.URL_TOKEN_BYTES)

    @cached_property
    def hmac(self) -> str:
        """Returns HMAC hash calculated from token, `flask.current_app.secret_key` is used as secret."""
        return create_hmac_hexdigest(self.token, current_app.secret_key)
    
    @cached_property
    def shortened_url(self) -> str:
        """Returns the shortened URL using `flask.url_for`."""
        return url_for('main.short_url', token=self.token, _external=True)
    
    @cached_property
    def deletion_url(self) -> str:
        """Returns deletion URL using `flask.url_for`."""
        return url_for('api.delete_short_url', hmac_hash=self.hmac, token=self.token, _external=True)

    def is_valid(self) -> bool:
        """Checks if URL is valid"""
        if self.url is None:
            return False

        if not self.url.startswith(('https://', 'http://')):
            self.url = 'https://{}'.format(self.url)

        parsed = urlparse(self.url)

        # Parsed URL must have at least scheme and netloc (e.g. domain name)
        try:    
            return all([parsed.scheme, parsed.netloc]) and parsed.netloc.split('.')[1]
        except IndexError:
            return False

    def add(self):
        """Inserts the URL and token to database."""
        self.cursor.execute("INSERT INTO urls VALUES (?, ?)", (
            self.token,
            self.url
        ))
        self.db.commit()
    
    def embed(self) -> ShortUrlEmbed:
        """Returns ShorturlEmbed instance for this URL."""
        embed = ShortUrlEmbed(
            content_url=self.shortened_url, 
            deletion_url=self.deletion_url, 
            original_url=self.url, 
            shortened_url=self.shortened_url
        )
        return embed

    @classmethod
    def get_by_token(cls, token: str):
        """Returns the URL for given token from database."""
        instance = cls()
        result = instance.cursor.execute("SELECT url FROM urls WHERE token = ?", (token,))
        row = result.fetchone()
        if row is None:
            return None
        return row[0]

    @classmethod
    def delete(cls, token: str) -> bool:
        """DELETEs URL using given token from database."""
        instance = cls()
        execute = instance.cursor.execute("DELETE FROM urls WHERE token = ?", (token,))
        instance.db.commit()
        return execute.rowcount > 0

    def __get_db(self):
        conn = sqlite3.connect('urls.db')
        query = "CREATE TABLE IF NOT EXISTS urls (token VARCHAR(10) NOT NULL PRIMARY KEY, url TEXT NOT NULL)"
        conn.execute(query)
        return conn