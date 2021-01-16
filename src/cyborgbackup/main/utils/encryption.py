import os
import stat
import errno
import base64
import hashlib
import logging
import tempfile
from collections import namedtuple

import six
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.backends import default_backend
from django.utils.encoding import smart_str

__all__ = ['get_encryption_key',
           'encrypt_field', 'decrypt_field',
           'encrypt_value', 'decrypt_value',
           'encrypt_dict', 'is_encrypted']

logger = logging.getLogger('cyborgbackup.main.utils.encryption')


class Fernet256(Fernet):
    '''Not techincally Fernet, but uses the base of the Fernet spec and uses AES-256-CBC
    instead of AES-128-CBC. All other functionality remain identical.
    '''

    def __init__(self, key, backend=None):
        if backend is None:
            backend = default_backend()

        key = base64.urlsafe_b64decode(key)
        if len(key) != 64:
            raise ValueError(
                "Fernet key must be 64 url-safe base64-encoded bytes."
            )

        self._signing_key = key[:32]
        self._encryption_key = key[32:]
        self._backend = backend


def get_encryption_key(field_name, pk=None):
    '''
    Generate key for encrypted password based on field name,
    ``settings.SECRET_KEY``, and instance pk (if available).

    :param pk: (optional) the primary key of the model object;
               can be omitted in situations where you're encrypting a setting
               that is not database-persistent (like a read-only setting)
    '''
    from django.conf import settings
    h = hashlib.sha512()
    h.update(settings.SECRET_KEY.encode('utf-8'))
    if pk is not None:
        h.update(str(pk).encode('utf-8'))
    h.update(field_name.encode('utf-8'))
    return base64.urlsafe_b64encode(h.digest())


def encrypt_value(value, pk=None):
    TransientField = namedtuple('TransientField', ['pk', 'value'])
    return encrypt_field(TransientField(pk=pk, value=value), 'value')


def encrypt_field(instance, field_name, ask=False, subfield=None, skip_utf8=False):
    '''
    Return content of the given instance and field name encrypted.
    '''
    value = getattr(instance, field_name)
    if isinstance(value, dict) and subfield is not None:
        value = value[subfield]
    if not value or value.startswith('$encrypted$') or (ask and value == 'ASK'):
        return value
    if skip_utf8:
        utf8 = False
    else:
        utf8 = type(value) == six.text_type
    value = smart_str(value)
    key = get_encryption_key(field_name, getattr(instance, 'pk', None))
    f = Fernet256(key)
    encrypted = f.encrypt(value.encode('utf-8'))
    b64data = base64.b64encode(encrypted)
    tokens = ['$encrypted', 'AESCBC', b64data.decode('utf-8')]
    if utf8:
        # If the value to encrypt is utf-8, we need to add a marker so we
        # know to decode the data when it's decrypted later
        tokens.insert(1, 'UTF8')
    return '$'.join(tokens)


def decrypt_value(encryption_key, value):
    raw_data = value[len('$encrypted$'):]
    # If the encrypted string contains a UTF8 marker, discard it
    utf8 = raw_data.startswith('UTF8$')
    if utf8:
        raw_data = raw_data[len('UTF8$'):]
    algo, b64data = raw_data.split('$', 1)
    if algo != 'AESCBC':
        raise ValueError('unsupported algorithm: %s' % algo)
    encrypted = base64.b64decode(b64data)
    f = Fernet256(encryption_key)
    value = f.decrypt(encrypted)
    # If the encrypted string contained a UTF8 marker, decode the data
    if utf8:
        value = value.decode('utf-8')
    return value


def decrypt_field(instance, field_name, subfield=None):
    '''
    Return content of the given instance and field name decrypted.
    '''
    value = getattr(instance, field_name)
    if isinstance(value, dict) and subfield is not None:
        value = value[subfield]
    if not value or not value.startswith('$encrypted$'):
        return value
    key = get_encryption_key(field_name, getattr(instance, 'pk', None))

    try:
        return decrypt_value(key, value)
    except InvalidToken:
        logger.exception(
            "Failed to decrypt `%s(pk=%s).%s`; if you've recently restored from "
            "a database backup or are running in a clustered environment, "
            "check that your `SECRET_KEY` value is correct",
            instance.__class__.__name__,
            getattr(instance, 'pk', None),
            field_name,
            exc_info=True
        )
        raise


def encrypt_dict(data, fields):
    '''
    Encrypts all of the dictionary values in `data` under the keys in `fields`
    in-place operation on `data`
    '''
    encrypt_fields = set(data.keys()).intersection(fields)
    for key in encrypt_fields:
        data[key] = encrypt_value(data[key])


def is_encrypted(value):
    if not isinstance(value, six.string_types):
        return False
    return value.startswith('$encrypted$') and len(value) > len('$encrypted$')


class KeypairError(Exception):
    pass


class Keypair(object):

    def __init__(self, size=256, type='ed25519', comment='cyborg@cyborg.local', passphrase=None):
        self.path = self.generate_temporary_filename()
        self.size = size
        self.type = type
        self.comment = comment
        self.changed = False
        self.privatekey = None
        self.fingerprint = {}
        self.public_key = {}
        self.passphrase = passphrase

        if self.type in 'rsa':
            self.size = 4096 if self.size is None else self.size
            if self.size < 1024:
                raise KeypairError('For RSA keys, the minimum size is 1024 bits and the default is 4096 bits. '
                                   'Attempting to use bit lengths under 1024 will cause the module to fail.')

        if self.type == 'dsa':
            self.size = 1024 if self.size is None else self.size
            if self.size != 1024:
                raise KeypairError('DSA keys must be exactly 1024 bits as specified by FIPS 186-2.')

        if self.type == 'ecdsa':
            self.size = 256 if self.size is None else self.size
            if self.size not in (256, 384, 521):
                raise KeypairError('For ECDSA keys, size determines the key length by selecting from '
                                   'one of three elliptic curve sizes: 256, 384 or 521 bits. '
                                   'Attempting to use bit lengths other than these three values for '
                                   'ECDSA keys will cause this module to fail. ')
        if self.type == 'ed25519':
            self.size = 256

        if not self.passphrase:
            self.generate_passphrase()

    def generate_passphrase(self):
        import string
        import random
        letters_and_digits = string.ascii_letters + string.digits
        self.passphrase = ''.join((random.choice(letters_and_digits) for i in range(40)))

    @staticmethod
    def generate_temporary_filename():
        import string
        import random
        letters_and_digits = string.ascii_letters + string.digits
        return '/tmp/tmpcyborg_'+''.join((random.choice(letters_and_digits) for i in range(15)))

    def generate(self):
        import subprocess
        args = [
            'ssh-keygen',
            '-q',
            '-N', '',
            '-b', str(self.size),
            '-t', self.type,
            '-f', self.path,
        ]

        if self.comment:
            args.extend(['-C', self.comment])
        else:
            args.extend(['-C', ""])

        try:
            if os.path.exists(self.path) and not os.access(self.path, os.W_OK):
                os.chmod(self.path, stat.S_IWUSR + stat.S_IRUSR)
            subprocess.run(args)
            with open(self.path) as f:
                self.privatekey = f.read()
            proc = subprocess.run(['ssh-keygen', '-lf', self.path], stdout=subprocess.PIPE)
            self.fingerprint = proc.stdout.split()
            pubkey = subprocess.run(['ssh-keygen', '-yf', self.path], stdout=subprocess.PIPE)
            self.public_key = pubkey.stdout.strip(b'\n')
        except Exception as e:
            raise e
        finally:
            self.remove()

    @staticmethod
    def get_publickey(privatekey):
        import subprocess
        f = tempfile.NamedTemporaryFile(delete=False)
        f.write(privatekey.encode('utf-8'))
        f.close()
        pubkey = subprocess.run(['ssh-keygen', '-yf', f.name], stdout=subprocess.PIPE)
        os.unlink(f.name)
        return pubkey.stdout.strip(b'\n')

    def remove(self):
        """Remove the resource from the filesystem."""

        try:
            os.remove(self.path)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise KeypairError(exc)
            else:
                pass

        if os.path.exists(self.path + ".pub"):
            try:
                os.remove(self.path + ".pub")
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise KeypairError(exc)
                else:
                    pass