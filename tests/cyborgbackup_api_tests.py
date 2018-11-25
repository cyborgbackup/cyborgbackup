#! /usr/bin/env python
import os
import sys
import cyborgbackup
import unittest
import OpenSSL
import json
import tempfile
import base64
import pwd
from io import StringIO
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime, timedelta
import logging

if sys.version_info < (3, 4):
    import imp as importlib
else:
    import importlib

for h in logging.getLogger().handlers:
    logging.getLogger().removeHandler(h)
logging.getLogger().addHandler(logging.NullHandler())


class Object(object):
    data = None
    status_code = None


def init_db():
    db = TinyDB(manpki.config.ManPKIObject.dbdir + "/manpki.json")
    db.purge_tables()

    exten = db.table('extension')
    exten.insert({'type': 'keyusage', 'oid': '2.5.29.15.0', 'name': 'digitalSignature', '_default': True})
    exten.insert({'type': 'keyusage', 'oid': '2.5.29.15.1', 'name': 'nonRepudiation', '_default': True})
    exten.insert({'type': 'keyusage', 'oid': '2.5.29.15.2', 'name': 'keyEncipherment', '_default': True})
    exten.insert({'type': 'keyusage', 'oid': '2.5.29.15.3', 'name': 'dataEncipherment', '_default': True})
    exten.insert({'type': 'keyusage', 'oid': '2.5.29.15.4', 'name': 'keyAgreement', '_default': True})
    exten.insert({'type': 'keyusage', 'oid': '2.5.29.15.5', 'name': 'keyCertSign', '_default': True})
    exten.insert({'type': 'keyusage', 'oid': '2.5.29.15.6', 'name': 'cRLSign', '_default': True})
    exten.insert({'type': 'keyusage', 'oid': '2.5.29.15.7', 'name': 'encipherOnly', '_default': True})
    exten.insert({'type': 'keyusage', 'oid': '2.5.29.15.8', 'name': 'decipherOnly', '_default': True})
    exten.insert(
        {'type': 'extended', 'oid': '1.3.6.1.5.5.7.3.1', 'name': 'TLS Web Server Authentication', '_default': True})

    profile = db.table('profile')
    profile.insert(
        {'name': 'SSLServer', 'keyusage': '2.5.29.15.3|2.5.29.15.2|2.5.29.15.1', 'extended': '1.3.6.1.5.5.7.3.1',
         'ldap': '', '_default': True})

    param = db.table('parameter')
    param.insert(
        {'object': 'ca', 'email': 'test@manpki.com', 'validity': 3560, 'keysize': 2048, 'basecn': 'C=FR', 'name': 'CA',
         'digest': 'sha256',
         'typeca': 'rootca', 'isfinal': True})
    param.insert({'object': 'cert', 'validity': 365, 'keysize': 1024, 'digest': 'sha256'})
    param.insert({'object': 'crl', 'enable': False, 'digest': 'md5', 'validity': 30})
    param.insert({'object': 'ocsp', 'enable': False, 'uri': 'http://ocsp/'})
    param.insert(
        {'object': 'ldap', 'enable': False, 'host': 'ldap://ldap:389/', 'dn': 'cn=admin', 'password': 'password',
         'mode': 'ondemand', 'schedule': '5m'})

    param.insert({'object': 'mail', 'enable': False, 'host': 'smtp', 'sender': 'manpki@example.com'})
    param.insert({'object': 'server', 'sslcert': 'cert.pem', 'sslkey': 'key.pem', 'host': 'socket', 'port': 8080})

    user = db.table('user')
    user.insert({'object': 'user', 'username': pwd.getpwuid(os.getuid())[0], 'roles': [{'role': 'admin'}]})

    db.close()


class ManpkiTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = self.db_fd.name
        self.db_fd.close()
        manpki.server.app.config['DATABASE'] = self.db_path
        init_db()
        self.app = manpki.server.app.test_client()
        unittest.installHandler()

    def tearDown(self):
        os.unlink(self.db_path)

    def open_with_auth(self, url, method, username, password, data=None):
        return self.app.open(url,
                             method=method,
                             data=data,
                             content_type='application/json',
                             headers={
                                 'Content-type': 'application/json',
                                 'Authorization': 'Basic ' + base64.b64encode(
                                     bytes(username + ":" + password, 'ascii')).decode('ascii')
                             }
                             )

    def login(self, username):
        return self.open_with_auth('/login', 'GET', username, 'null')

    def logout(self, username):
        return self.open_with_auth('/logout', 'GET', username, 'null')

    def _query(self, path, method, datapost=None):
        rv = self.login(pwd.getpwuid(os.getuid())[0])
        data = json.loads(rv.data.decode('utf-8'))
        secret = data['secret']
        rv = self.open_with_auth(path, method, pwd.getpwuid(os.getuid())[0], 'null', data=datapost)
        data = json.loads(rv.data.decode('utf-8'))
        signed = jose.jws.verify(data, secret, algorithms=['HS256'])
        decoded = json.loads(signed.decode("utf8"))

        newrv = Object()
        newrv.__dict__ = rv.__dict__.copy()
        newrv.status_code = newrv._status_code
        newrv.status = newrv._status
        newrv.data = decoded
        return newrv

    def get(self, path):
        return self._query(path, 'GET')

    def post(self, path, data):
        return self._query(path, 'POST', data)

    def put(self, path, data=None):
        return self._query(path, 'PUT', data)

    def delete(self, path):
        return self._query(path, 'DELETE')

    def test_manpki_show_version(self):
        with patch('sys.stdout', new=StringIO()) as fakeOutput:
            manpki.show_version()
            msg = "ManPKI by {}\nVersion : {}".format(manpki.AUTHOR, manpki.VERSION)
            self.assertEqual(fakeOutput.getvalue().strip(), msg)

    def test_manpki_config_get_none_config_directory(self):
        import builtins
        builtins.DEBUG = True
        importlib.reload(manpki.config)
        config_dir = manpki.config.get_config_directory([])
        self.assertIsNone(config_dir)

    def test_manpki_config_get_none_config_file(self):
        import builtins
        builtins.DEBUG = True
        importlib.reload(manpki.config)
        config_dir = manpki.config.get_config_file([])
        self.assertEqual(list(config_dir), [])

    def test_manpki_config_get_none_var_directory(self):
        import builtins
        builtins.DEBUG = True
        importlib.reload(manpki.config)
        var_dir = manpki.config.get_var_directory([])
        self.assertIsNone(var_dir)

    def test_manpki_config_get_none_run_directory(self):
        import builtins
        builtins.DEBUG = True
        importlib.reload(manpki.config)
        run_dir = manpki.config.get_run_directory([])
        self.assertIsNone(run_dir)

    def test_manpki_config_override_logfile(self):
        self.assertEqual(manpki.config.LOGFILE, '/var/log/manpki/manpkid.log')
        import builtins
        builtins.LOGFILE = '/tmp/toto.log'
        importlib.reload(manpki.config)
        self.assertEqual(manpki.config.LOGFILE, '/tmp/toto.log')

    def test_manpki_config_override_daemon(self):
        self.assertFalse(manpki.config.DAEMON)
        import builtins
        builtins.DAEMON = True
        importlib.reload(manpki.config)
        self.assertTrue(manpki.config.DAEMON)

    def test_manpki_api_page_not_found(self):
        rv = self.app.get('/not_a_page')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(json.loads(rv.data.decode('utf-8')), {'error': 'Page not found'})

    def test_manpki_api_method_not_allowed(self):
        rv = self.app.open('/', method='METHOD')
        self.assertEqual(rv.status_code, 405)
        self.assertEqual(json.loads(rv.data.decode('utf-8')), {'error': 'Method not allowed'})

    def test_manpki_api_entry_point(self):
        rv = self.app.get('/')
        self.assertEqual(rv.data.decode('utf-8'), 'Welcome to the ManPKI API. Please read API documentation.')

    def test_manpki_api_ping(self):
        rv = self.app.get('/ping')
        self.assertEqual(rv.status_code, 200)
        remote_data = json.loads(rv.data.decode('utf-8'))
        self.assertEqual(len(remote_data), 3)
        data_keys = list(remote_data.keys())
        data_keys.sort()
        self.assertEqual(data_keys, ["hostname", "message", "secret"])
        self.assertEqual(remote_data['message'], "pong")
        self.assertEqual(remote_data['hostname'], os.uname()[1])
        self.assertGreater(len(remote_data['secret']), 0)

    def test_manpki_api_correct_login(self):
        rv = self.login(pwd.getpwuid(os.getuid())[0])
        self.assertEqual(rv.status_code, 200)
        remote_data = json.loads(rv.data.decode('utf-8'))
        self.assertEqual(len(remote_data), 4)
        data_keys = list(remote_data.keys())
        data_keys.sort()
        self.assertEqual(data_keys, ["hostname", "message", "secret", "token"])
        self.assertEqual(remote_data['message'], "login")
        self.assertEqual(remote_data['hostname'], os.uname()[1])
        self.assertGreater(len(remote_data['secret']), 0)
        self.assertGreater(len(remote_data['token']), 0)

    def test_manpki_api_incorrect_login(self):
        rv = self.login('tintin')
        self.assertEqual(rv.status_code, 401)
        self.assertEqual(rv.data.decode('utf-8'), 'Unauthorized Access')

    def test_manpki_api_logout(self):
        self.login(pwd.getpwuid(os.getuid())[0])
        rv = self.logout(pwd.getpwuid(os.getuid())[0])
        self.assertEqual(rv.status_code, 200)
        remote_data = json.loads(rv.data.decode('utf-8'))
        self.assertEqual(len(remote_data), 2)
        self.assertEqual(remote_data['message'], "logout")
        self.assertEqual(remote_data['hostname'], os.uname()[1])

    def test_manpki_api_info_not_logged(self):
        rv = self.app.get('/info')
        self.assertEqual(rv.status_code, 401)
        self.assertEqual(rv.data.decode('utf-8'), 'Unauthorized Access')

    def test_manpki_api_info_logged(self):
        rv = self.get('/info')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 5)
        self.assertEqual(rv.data['message'], "info")
        self.assertEqual(rv.data['hostname'], os.uname()[1])
        self.assertEqual(rv.data['username'], pwd.getpwuid(os.getuid())[0])

    def test_manpki_api_render(self):
        rv = self.get('/render')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertNotEqual(rv.data['render'], None)
        self.assertIsInstance(rv.data['render'], dict)

    def test_manpki_api_discovery(self):
        rv = self.get('/discovery')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertGreater(len(rv.data['api']), 1)

    def test_manpki_api_locales_fr_unknown(self):
        rv = self.get('/locale/fr')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['lang'], 'fr')
        self.assertEqual(rv.data['locales'], None)

    def test_manpki_api_locales_fr_FR_unknown(self):
        rv = self.get('/locale/fr_FR')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['lang'], 'fr_FR')
        self.assertEqual(rv.data['locales'], None)

    def test_manpki_api_locales_fr_FR_utf8_correct(self):
        rv = self.get('/locale/fr_FR.UTF-8')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['lang'], 'fr_FR.UTF-8')
        self.assertNotEqual(rv.data['locales'], None)
        self.assertIsInstance(rv.data['locales'], dict)

    def test_manpki_api_ca_create(self):
        manpki.tools.ssl.SSL.delete_ca()
        date_before_create = datetime.utcnow().replace(microsecond=0)
        rv = self.put('/v1.0/ca')
        date_after_create = datetime.utcnow()
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['message'], 'ca created')
        ca = rv.data['ca']
        cn = "C=FR, CN=CA, emailAddress=test@manpki.com"
        date_ca_before = datetime.strptime(ca['notbefore'], "%a %b %d %H:%M:%S %Y %Z")
        date_ca_after = datetime.strptime(ca['notafter'], "%a %b %d %H:%M:%S %Y %Z")
        self.assertEqual(ca['issuer'], cn)
        self.assertEqual(ca['subject'], cn)
        self.assertEqual(ca['keysize'], 2048)
        self.assertGreaterEqual(date_ca_before, date_before_create)
        self.assertLessEqual(date_ca_before, date_after_create)
        self.assertGreaterEqual(date_ca_after, date_before_create + timedelta(days=3560))
        self.assertLessEqual(date_ca_after, date_after_create + timedelta(days=3560))

        ca_cert = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, ca['raw'])
        self.assertEqual(ca_cert.get_version(), 2)
        self.assertTrue(ca_cert.get_extension(0).get_critical())
        self.assertEqual(ca_cert.get_extension(0).get_short_name(), b'basicConstraints')
        self.assertEqual(ca_cert.get_extension(0).__str__(), "CA:TRUE, pathlen:0")
        self.assertTrue(ca_cert.get_extension(1).get_critical())
        self.assertEqual(ca_cert.get_extension(1).get_short_name(), b'keyUsage')
        self.assertEqual(ca_cert.get_extension(1).__str__(), "Certificate Sign, CRL Sign")

    def test_manpki_api_ca_create_already_exist_without_force(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['error'], 'CA already exist')

    def test_manpki_api_ca_create_already_exist_with_force(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        rv = self.put('/v1.0/ca', data='{"force": true}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['message'], 'ca created with force')

    @patch('manpki.tools.ssl.SSL.create_ca', return_value=None)
    def test_manpki_api_ca_create_with_error(self, mock_create_ca):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['error'], 'unable to create the ca')

    def test_manpki_api_ca_create_already_exist_with_create_error(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        with patch('manpki.tools.ssl.SSL.create_ca', return_value=False) as mock_create_ca:
            rv = self.put('/v1.0/ca', data='{"force": true}')
            self.assertEqual(rv.status_code, 404)
            self.assertEqual(len(rv.data), 1)
            self.assertEqual(rv.data['error'], 'unable to create the ca')

    def test_manpki_api_ca_create_already_exist_with_deletion_error(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        with patch('manpki.tools.ssl.SSL.delete_ca', return_value=False) as mock_create_ca:
            rv = self.put('/v1.0/ca', data='{"force": true}')
            self.assertEqual(rv.status_code, 404)
            self.assertEqual(len(rv.data), 1)
            self.assertEqual(rv.data['error'], 'unable to create the ca')

    def test_manpki_api_ca_delete_ok(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        rv = self.delete('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['ca'], 'deleted')

    def test_manpki_api_ca_delete_ca_with_error(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        with patch('os.unlink') as mock_os_unlink:
            mock_os_unlink.side_effect = OSError('Some error was thrown')
            rv = self.delete('/v1.0/ca')
            self.assertEqual(rv.status_code, 404)
            self.assertEqual(len(rv.data), 1)
            self.assertEqual(rv.data['ca'], 'error with deletion')

    def test_manpki_api_show_ca_not_create(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.get('/v1.0/ca')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['error'], 'CA not ready')

    def test_manpki_api_show_ca_create(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        rv = self.get('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertGreater(len(rv.data['ca']), 1)
        data_keys = list(rv.data['ca'].keys())
        data_keys.sort()
        self.assertEqual(data_keys,
                         ['algorithm', 'finger_md5', 'finger_sha1', 'id', 'issuer', 'keysize', 'notafter', 'notbefore',
                          'raw', 'serial', 'signature', 'state', 'subject', 'version'])

    def test_manpki_api_set_ca_param_success_one(self):
        rv = self.post('/v1.0/ca/param', data='{"basecn": "ChangeCN"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['state'], 'OK')

    def test_manpki_api_set_ca_param_success_multiple(self):
        rv = self.post('/v1.0/ca/param', data='{"basecn": "ChangeCN-2", "keysize": 1024}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['state'], 'OK')

    def test_manpki_api_set_ca_param_not_success(self):
        rv = self.post('/v1.0/ca/param', data='{"lorem": "ipsum", "keysize": 1024}')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['error'], 'CA param not valid')

    def test_manpki_api_get_ca_param_all(self):
        rv = self.post('/v1.0/ca/param', data='{"basecn": "C=EU", "keysize": 2047, "email": "test@manpki.co"}')
        self.assertEqual(rv.status_code, 200)
        rv = self.get('/v1.0/ca/param/')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 8)
        keys = list(rv.data.keys())
        keys.sort()
        self.assertEqual(keys, ["basecn","digest","email","isfinal","keysize","name","typeca","validity"])
        self.assertEqual(rv.data['basecn'], "C=EU")
        self.assertEqual(rv.data['keysize'], 2047)
        self.assertEqual(rv.data['email'], "test@manpki.co")
        self.assertEqual(rv.data['validity'], 3560)

    def test_manpki_api_get_ca_param_specified(self):
        rv = self.post('/v1.0/ca/param', data='{"basecn": "C=NE", "keysize": 2046, "email": "test@manpki.c"}')
        self.assertEqual(rv.status_code, 200)
        rv = self.get('/v1.0/ca/param/basecn')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['basecn'], "C=NE")

    # def test_manpki_api_delete_ca_success(self):
    #     manpki.tools.ssl.SSL.delete_ca()
    #     rv = self.put('/v1.0/ca')
    #     self.assertEqual(rv.status_code, 200)
    #     rv = self.delete('/v1.0/ca')
    #     print(rv.data)
    #     self.assertEqual(rv.status_code, 200)
    #
    # def test_manpki_api_delete_ca_not_success(self):
    #     manpki.tools.ssl.SSL.delete_ca()
    #     rv = self.delete('/v1.0/ca')
    #     print(rv.data)
    #     self.assertEqual(rv.status_code, 404)

    def test_manpki_api_cert_create(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        ca = rv.data['ca']
        date_before_create = datetime.utcnow().replace(microsecond=0)
        rv = self.put('/v1.0/cert', data='{"cn": "TestCert1", "mail": "testcert@manpki.com", "profile":"SSLServer"}')
        date_after_create = datetime.utcnow()
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 3)
        self.assertEqual(rv.data['message'], 'certificate created')
        cert = rv.data['cert']
        cn = "C=FR, CN=TestCert1, emailAddress=testcert@manpki.com"
        date_cert_before = datetime.strptime(cert['notbefore'], "%a %b %d %H:%M:%S %Y %Z")
        date_cert_after = datetime.strptime(cert['notafter'], "%a %b %d %H:%M:%S %Y %Z")
        self.assertEqual(cert['issuer'], ca['subject'])
        self.assertEqual(cert['subject'], cn)
        self.assertEqual(cert['keysize'], 1024)
        self.assertGreaterEqual(date_cert_before, date_before_create)
        self.assertLessEqual(date_cert_before, date_after_create)
        self.assertGreaterEqual(date_cert_after, date_before_create + timedelta(days=365))
        self.assertLessEqual(date_cert_after, date_after_create + timedelta(days=365))

        cert = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert['raw'])
        self.assertEqual(cert.get_version(), 2)
        self.assertTrue(cert.get_extension(0).get_critical())
        self.assertEqual(cert.get_extension(0).get_short_name(), b'basicConstraints')
        self.assertEqual(cert.get_extension(0).__str__(), "CA:FALSE")
        self.assertTrue(cert.get_extension(1).get_critical())
        self.assertEqual(cert.get_extension(1).get_short_name(), b'keyUsage')
        self.assertEqual(cert.get_extension(1).__str__(), "Non Repudiation, Key Encipherment, Data Encipherment")

    def test_manpki_api_cert_create_without_ca(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/cert', data='{"cn": "TestCert1", "mail": "testcert@manpki.com", "profile":"SSLServer"}')
        self.assertEqual(rv.status_code, 500)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['error'], 'ca must be created before create new certificate')

    def test_manpki_api_cert_create_not_enough_param(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        rv = self.put('/v1.0/cert', data='{"cn": "TestCert1"}')
        self.assertEqual(rv.status_code, 505)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['error'], 'missing parameter')

    # def test_manpki_api_cert_create_already_exist_without_force(self):
    #     manpki.tools.ssl.SSL.delete_ca()
    #     rv = self.put('/v1.0/ca')
    #     self.assertEqual(rv.status_code, 200)
    #     rv = self.put('/v1.0/ca')
    #     self.assertEqual(rv.status_code, 404)
    #     self.assertEqual(len(rv.data), 1)
    #     self.assertEqual(rv.data['error'], 'CA already exist')
    #
    # def test_manpki_api_cert_create_already_exist_with_force(self):
    #     manpki.tools.ssl.SSL.delete_ca()
    #     rv = self.put('/v1.0/ca')
    #     self.assertEqual(rv.status_code, 200)
    #     rv = self.put('/v1.0/ca', data='{"force": true}')
    #     self.assertEqual(rv.status_code, 200)
    #     self.assertEqual(len(rv.data), 2)
    #     self.assertEqual(rv.data['message'], 'ca created with force')

    def test_manpki_api_show_cert_not_create(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        rv = self.get('/v1.0/cert/')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['cert'], [])

    def test_manpki_api_show_cert_bad_id(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        rv = self.get('/v1.0/cert/0123456789')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['cert'], 'notexist')

    def test_manpki_api_show_cert_one_cert(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        rv = self.put('/v1.0/cert', data='{"cn": "TestCert2", "mail": "testcert2@manpki.com", "profile":"SSLServer"}')
        self.assertEqual(rv.status_code, 200)
        cert = rv.data['cert']
        rv = self.get('/v1.0/cert/'+cert['id'])
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        data_keys = list(rv.data['cert'].keys())
        data_keys.sort()
        self.assertEqual(data_keys,
                         ['algorithm', 'finger_md5', 'finger_sha1', 'id', 'issuer', 'keysize', 'notafter', 'notbefore',
                          'raw', 'serial', 'signature', 'state', 'subject', 'version'])

    def test_manpki_api_set_cert_param_success_one(self):
        rv = self.post('/v1.0/cert/set', data='{"keysize": 1024}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['state'], 'OK')

    def test_manpki_api_set_cert_param_success_multiple(self):
        rv = self.post('/v1.0/cert/set', data='{"keysize": 1025, "digest": "md5"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['state'], 'OK')

    def test_manpki_api_set_cert_param_not_success(self):
        rv = self.post('/v1.0/cert/set', data='{"lorem": "ipsum", "keysize": 1026}')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['error'], 'Certificate parameter not valid')

    def test_manpki_api_get_cert_param_all(self):
        rv = self.post('/v1.0/cert/set', data='{"keysize": 1027, "validity": 30, "digest": "sha1"}')
        self.assertEqual(rv.status_code, 200)
        rv = self.get('/v1.0/cert/param/')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 3)
        keys = list(rv.data.keys())
        keys.sort()
        self.assertEqual(keys, ["digest", "keysize", "validity"])
        self.assertEqual(rv.data['digest'], "sha1")
        self.assertEqual(rv.data['keysize'], 1027)
        self.assertEqual(rv.data['validity'], 30)

    def test_manpki_api_get_cert_param_specified(self):
        rv = self.post('/v1.0/cert/set', data='{"keysize": 1028, "digest": "sha128"}')
        self.assertEqual(rv.status_code, 200)
        rv = self.get('/v1.0/cert/param/keysize')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['keysize'], 1028)

    def test_manpki_api_new_profile_already_exist(self):
        rv = self.put('/v1.0/profile/SSLServer')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['error'], "alreadyexist")
        self.assertEqual(rv.data['profile'], "SSLServer")

    def test_manpki_api_new_profile(self):
        rv = self.put('/v1.0/profile/SSLTest', data='{"keyusage": "2.5.29.15.4"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['message'], "ok")
        self.assertEqual(rv.data['profile'], "SSLTest")

    def test_manpki_api_set_profile_default(self):
        rv = self.post('/v1.0/profile/SSLServer', data='{"keyusage": "2.5.29.15.4"}')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['error'], "defaultprofile")
        self.assertEqual(rv.data['profile'], "SSLServer")

    def test_manpki_api_set_profile_not_exist(self):
        rv = self.post('/v1.0/profile/SSLNotExist', data='{"keyusage": "2.5.29.15.4"}')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['error'], "notexist")
        self.assertEqual(rv.data['profile'], "SSLNotExist")

    def test_manpki_api_set_profile(self):
        rv = self.put('/v1.0/profile/SSLTest', data='{"keyusage": "2.5.29.15.4"}')
        self.assertEqual(rv.status_code, 200)
        rv = self.post('/v1.0/profile/SSLTest', data='{"extended": "1.3.6.1.5.5.7.3.1"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['message'], "updated")
        self.assertEqual(rv.data['profile'], "SSLTest")

    def test_manpki_api_delete_profile_exist(self):
        rv = self.put('/v1.0/profile/SSLTest', data='{"keyusage": "2.5.29.15.4"}')
        self.assertEqual(rv.status_code, 200)
        rv = self.delete('/v1.0/profile/SSLTest')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['message'], "deleted")
        self.assertEqual(rv.data['profile'], "SSLTest")

    def test_manpki_api_delete_profile_not_exist(self):
        rv = self.delete('/v1.0/profile/SSLNotExist')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 3)
        self.assertEqual(rv.data['error'], "notexist")
        self.assertEqual(rv.data['profile'], "SSLNotExist")

    def test_manpki_api_delete_profile_default(self):
        rv = self.delete('/v1.0/profile/SSLServer')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['error'], "defaultprofile")
        self.assertEqual(rv.data['profile'], "SSLServer")

    def test_manpki_api_show_profile_default(self):
        rv = self.get('/v1.0/profile/')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['profile'], [
            {"default": True, "ldap": "", "name": "SSLServer", "keyusage": "2.5.29.15.3|2.5.29.15.2|2.5.29.15.1",
             "extended": "1.3.6.1.5.5.7.3.1"}])

    def test_manpki_api_show_profile_one_exist_profile(self):
        rv = self.get('/v1.0/profile/SSLServer')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['profile'],
            {"default": True, "ldap": "", "name": "SSLServer", "keyusage": "2.5.29.15.3|2.5.29.15.2|2.5.29.15.1",
             "extended": "1.3.6.1.5.5.7.3.1"})

    def test_manpki_api_show_profile_not_exist_profile(self):
        rv = self.get('/v1.0/profile/SSLTest')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['profile'], "SSLTest")
        self.assertEqual(rv.data['error'], "notexist")

    def test_manpki_api_new_extension_already_exist(self):
        rv = self.put('/v1.0/extension/1.3.6.1.5.5.7.3.1')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['error'], "alreadyexist")
        self.assertEqual(rv.data['oid'], "1.3.6.1.5.5.7.3.1")

    def test_manpki_api_new_extension_with_correct_param(self):
        rv = self.put('/v1.0/extension/1.3.6.1.5.5.7.3.3', data='{"name": "Code Signing", "type":"extended"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['message'], "ok")
        self.assertEqual(rv.data['oid'], "1.3.6.1.5.5.7.3.3")

    def test_manpki_api_new_extension_with_incorrect_type(self):
        rv = self.put('/v1.0/extension/1.3.6.1.5.5.7.3.3', data='{"name": "Code Signing", "type":"toto"}')
        self.assertEqual(rv.status_code, 500)
        self.assertEqual(len(rv.data), 3)
        self.assertEqual(rv.data['error'], "missingtypeorname")
        self.assertEqual(rv.data['oid'], "1.3.6.1.5.5.7.3.3")

    def test_manpki_api_new_extension_with_missing_param(self):
        rv = self.put('/v1.0/extension/1.3.6.1.5.5.7.3.3', data='{"type":"toto"}')
        self.assertEqual(rv.status_code, 500)
        self.assertEqual(len(rv.data), 3)
        self.assertEqual(rv.data['error'], "missingtypeorname")
        self.assertEqual(rv.data['oid'], "1.3.6.1.5.5.7.3.3")

    def test_manpki_api_set_extension_default(self):
        rv = self.post('/v1.0/extension/2.5.29.15.0', data='{"type": "keyusage", "name": "Digital Sign"}')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['error'], "defaultextension")
        self.assertEqual(rv.data['oid'], "2.5.29.15.0")

    def test_manpki_api_set_extension_correct(self):
        rv = self.put('/v1.0/extension/1.3.6.1.5.5.7.3.3', data='{"name": "Code Signing", "type": "extended"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        rv = self.post('/v1.0/extension/1.3.6.1.5.5.7.3.3', data='{"name": "Sign of Code", "type": "keyusage"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['message'], "updated")
        self.assertEqual(rv.data['oid'], "1.3.6.1.5.5.7.3.3")

    def test_manpki_api_set_extension_not_exist(self):
        rv = self.post('/v1.0/extension/1.3.6.1.5.5.7.3.4', data='{"name": "Test of John Doe", "type": "keyusage"}')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['error'], "notexist")
        self.assertEqual(rv.data['oid'], "1.3.6.1.5.5.7.3.4")

    def test_manpki_api_delete_extension_exist(self):
        rv = self.put('/v1.0/extension/1.3.6.1.5.5.7.3.3', data='{"name": "Code Signing", "type": "extended"}')
        self.assertEqual(rv.status_code, 200)
        rv = self.delete('/v1.0/extension/1.3.6.1.5.5.7.3.3')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['message'], "deleted")
        self.assertEqual(rv.data['oid'], "1.3.6.1.5.5.7.3.3")

    def test_manpki_api_delete_extension_not_exist(self):
        rv = self.delete('/v1.0/extension/1.2.3.4.5.6.7.8.9')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 3)
        self.assertEqual(rv.data['error'], "notexist")
        self.assertEqual(rv.data['oid'], "1.2.3.4.5.6.7.8.9")

    def test_manpki_api_delete_extension_default(self):
        rv = self.delete('/v1.0/extension/1.3.6.1.5.5.7.3.1')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['error'], "defaultextension")
        self.assertEqual(rv.data['oid'], "1.3.6.1.5.5.7.3.1")

    def test_manpki_api_show_extension_default(self):
        rv = self.get('/v1.0/extension/')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(len(rv.data['extension']), 10)
        keys = list(rv.data['extension'][0].keys())
        keys.sort()
        self.assertEqual(keys, ["default", "name", "oid", "type"])

    def test_manpki_api_show_extension_one_exist_extension(self):
        rv = self.get('/v1.0/extension/2.5.29.15.1')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['extension'],
            {'type': 'keyusage', 'oid': '2.5.29.15.1', 'name': 'nonRepudiation', 'default': True})

    def test_manpki_api_show_extension_not_exist_profile(self):
        rv = self.get('/v1.0/extension/1.2.3.4.5.6.7.8.9')
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(rv.data), 2)
        self.assertEqual(rv.data['oid'], "1.2.3.4.5.6.7.8.9")
        self.assertEqual(rv.data['error'], "notexist")

    def test_manpki_api_show_server(self):
        rv = self.get('/v1.0/server')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['server'], {"host": "socket", "cert": "", "port": "0", "key": ""})

    @patch('signal.alarm', return_value=None)
    def test_manpki_api_restart_server(self, mock_reload):
        rv = self.get('/v1.0/server/restart')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['message'], "reload in 5 second")

    def test_manpki_api_set_server_with_socket(self):
        rv = self.post('/v1.0/server/set', data='{"host": "socket"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['message'], "ok")

    def test_manpki_api_set_server_with_host_ip(self):
        rv = self.post('/v1.0/server/set', data='{"host": "0.0.0.0"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['message'], "ok")

    def test_manpki_api_set_server_with_cert(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        rv = self.put('/v1.0/cert', data='{"cn": "TestCert2", "mail": "testcert2@manpki.com", "profile":"SSLServer"}')
        self.assertEqual(rv.status_code, 200)
        rv = self.post('/v1.0/server/set', data='{"host": "0.0.0.0", "port": "4443", "cert": "'+rv.data['certid']+'"}')
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.data), 1)
        self.assertEqual(rv.data['message'], "ok")

    def test_manpki_tools_isint(self):
        self.assertTrue(manpki.tools.isint(1))
        self.assertTrue(manpki.tools.isint(99999))
        self.assertTrue(manpki.tools.isint(2.0))
        self.assertTrue(manpki.tools.isint("5"))
        self.assertFalse(manpki.tools.isint(1.1))
        self.assertFalse(manpki.tools.isint(0.9))
        self.assertFalse(manpki.tools.isint("x"))
        self.assertFalse(manpki.tools.isint([]))
        self.assertFalse(manpki.tools.isint({}))

    def test_manpki_tools_isfloat(self):
        self.assertTrue(manpki.tools.isfloat(1.0))
        self.assertTrue(manpki.tools.isfloat(99999.9))
        self.assertTrue(manpki.tools.isfloat(2.0))
        self.assertTrue(manpki.tools.isfloat("5.3"))
        self.assertFalse(manpki.tools.isfloat(1))
        self.assertFalse(manpki.tools.isfloat(1000))
        self.assertFalse(manpki.tools.isfloat("x"))
        self.assertFalse(manpki.tools.isfloat([]))
        self.assertFalse(manpki.tools.isfloat({}))

    def test_manpki_tools_generate_sha256_string(self):
        ret = manpki.tools.generate_sha256_string()
        self.assertEqual(len(ret), (256 * 2)/8)
        self.assertRegex(ret, "[a-f0-9]{64}")

    def test_manpki_tools_error_response(self):
        msg, status = manpki.tools.error_response()
        self.assertEqual(status, 403)
        self.assertEqual(msg['error'], "Access denied")

    def test_manpki_tools_get_current_user_roles_anonymous(self):
        with self.app as c:
            rv = c.get('/ping')
            roles = manpki.tools.get_current_user_role()
        self.assertEqual(roles, 'anonymous')

    def test_manpki_tools_get_current_user_roles_admin(self):
        with self.app as c:
            c.open('/login',
                 method='GET',
                 content_type='application/json',
                 headers={
                     'Content-type': 'application/json',
                     'Authorization': 'Basic ' + base64.b64encode(
                         bytes(pwd.getpwuid(os.getuid())[0] + ":null", 'ascii')).decode('ascii')
                 }
            )
            roles = manpki.tools.get_current_user_role()
        self.assertEqual(roles, ['admin'])

    def test_manpki_tools_ssl_getparentca(self):
        path = manpki.tools.ssl.SSL.get_parentca_path()
        testpath = manpki.config.ManPKIObject.certdir + "/public/ca/parentca.crt"
        self.assertEqual(path, testpath)

    def test_manpki_tools_ssl_getcrlpath(self):
        path = manpki.tools.ssl.SSL.get_crl_path()
        testpath = manpki.config.ManPKIObject.certdir + "/public/ca/crl.pem"
        self.assertEqual(path, testpath)

    def test_manpki_tools_ssl_getcert_none(self):
        self.assertIsNone(manpki.tools.ssl.SSL.get_cert('toto'))
        self.assertIsNone(manpki.tools.ssl.SSL.get_cert(0))
        self.assertIsNone(manpki.tools.ssl.SSL.get_cert(None))

    def test_manpki_tools_ssl_generate_crl_with_ca(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(manpki.tools.ssl.SSL.generate_crl())

    def test_manpki_tools_ssl_generate_crl_without_ca(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        manpki.tools.ssl.SSL.delete_ca()
        self.assertFalse(manpki.tools.ssl.SSL.generate_crl())

    def test_manpki_tools_ssl_check_parentca(self):
        manpki.tools.ssl.SSL.delete_all_certs()
        manpki.tools.ssl.SSL.delete_ca()
        self.assertFalse(manpki.tools.ssl.SSL.check_parentca_exist())

    def test_manpki_tools_ssl_get_crl_exist(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(manpki.tools.ssl.SSL.generate_crl())
        crl = manpki.tools.ssl.SSL.get_crl()
        self.assertIsInstance(crl, OpenSSL.crypto.CRL)
        self.assertEqual(crl.get_issuer().hash(), 163884471)

    def test_manpki_tools_ssl_get_crl_notexist(self):
        manpki.tools.ssl.SSL.delete_ca()
        crl = manpki.tools.ssl.SSL.get_crl()
        self.assertIsNone(crl)

    def test_manpki_tools_ssl_get_crl_binary(self):
        manpki.tools.ssl.SSL.delete_ca()
        rv = self.put('/v1.0/ca')
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(manpki.tools.ssl.SSL.generate_crl())
        crlbin = manpki.tools.ssl.SSL.get_crl_binary()
        self.assertIsInstance(crlbin, bytes)

    def test_manpki_tools_ssl_get_json_all_certificates(self):
        manpki.tools.ssl.SSL.delete_ca()
        manpki.tools.ssl.SSL.create_ca()
        self.put('/v1.0/cert', data='{"cn": "TestCert1", "mail": "testcert@manpki.com", "profile":"SSLServer"}')
        self.put('/v1.0/cert', data='{"cn": "TestCert2", "mail": "testcert@manpki.com", "profile":"SSLServer"}')
        json = manpki.tools.ssl.SSL.get_json_all_certificates()
        self.assertEqual(len(json), 2)
        cert_one = json[0]
        data_keys = list(cert_one.keys())
        data_keys.sort()
        self.assertEqual(data_keys,
                         ['algorithm', 'finger_md5', 'finger_sha1', 'id', 'issuer', 'keysize', 'notafter', 'notbefore',
                          'raw', 'serial', 'signature', 'state', 'subject', 'version'])
        cert_one = json[1]
        data_keys = list(cert_one.keys())
        data_keys.sort()
        self.assertEqual(data_keys,
                         ['algorithm', 'finger_md5', 'finger_sha1', 'id', 'issuer', 'keysize', 'notafter', 'notbefore',
                          'raw', 'serial', 'signature', 'state', 'subject', 'version'])

    def test_manpki_tools_ssl_get_asn_cert_raw(self):
        manpki.tools.ssl.SSL.delete_ca()
        manpki.tools.ssl.SSL.create_ca()
        self.put('/v1.0/cert', data='{"cn": "TestCert1", "mail": "testcert@manpki.com", "profile":"SSLServer"}')
        certs = manpki.tools.ssl.SSL.get_all_certificates()
        self.assertEqual(len(certs), 1)
        id = certs[0]['id']
        asn_cert = manpki.tools.ssl.SSL.get_asn_cert_raw(id)
        self.assertIsInstance(asn_cert, bytes)

    def test_manpki_tools_ssl_create_extension(self):
        ext = manpki.tools.ssl.SSL.create_extension('keyUsage'.encode('utf8'), 'keyCertSign'.encode('utf8'), True)
        self.assertIsInstance(ext, OpenSSL.crypto.X509Extension)
        self.assertTrue(ext.get_critical())
        self.assertEqual(ext.get_short_name(), 'keyUsage'.encode('utf8'))

    def test_manpki_tools_ssl_generate_key(self):
        key = manpki.tools.ssl.SSL.create_key(1001)
        self.assertIsInstance(key, OpenSSL.crypto.PKey)
        self.assertEqual(key.bits(), 1001)
        self.assertEqual(key.type(), OpenSSL.crypto.TYPE_RSA)
        self.assertTrue(key.check())

    def test_manpki_tools_ssl_decode_time(self):
        strtime = "20170603120102Z"
        thedate = manpki.tools.ssl.SSL.decode_time(strtime.encode())
        self.assertIsInstance(thedate, datetime)
        self.assertEqual(thedate.year, 2017)
        self.assertEqual(thedate.month, 6)
        self.assertEqual(thedate.day, 3)
        self.assertEqual(thedate.hour, 12)
        self.assertEqual(thedate.minute, 1)
        self.assertEqual(thedate.second, 2)
        self.assertEqual(thedate.tzname(), 'UTC')

    def test_manpki_tools_ssl_create_request(self):
        key = manpki.tools.ssl.SSL.create_key(1002)
        req = manpki.tools.ssl.SSL.create_request(key)
        self.assertIsInstance(req, OpenSSL.crypto.X509Req)
        self.assertIsInstance(req.get_pubkey(), OpenSSL.crypto.PKey)
        self.assertEqual(req.get_pubkey().bits(), 1002)

    def test_manpki_tools_webssl_module(self):
        ret = manpki.tools.WebSSL._get_openssl_crypto_module()
        # @TODO : change pyCrypto to pyca
        self.assertEqual(type(ret), type(ret))

    def test_manpki_tools_webssl_adhocpair(self):
        webssl = manpki.tools.WebSSL()
        cert, pkey = webssl.generate_adhoc_ssl_pair(cn="Test")
        self.assertIsInstance(cert, OpenSSL.crypto.X509)
        self.assertIsInstance(pkey, OpenSSL.crypto.PKey)

    def test_manpki_tools_webssl_adhocpair_wildcard(self):
        webssl = manpki.tools.WebSSL()
        cert, pkey = webssl.generate_adhoc_ssl_pair()
        self.assertIsInstance(cert, OpenSSL.crypto.X509)
        self.assertIsInstance(pkey, OpenSSL.crypto.PKey)

    def test_manpki_tools_webssl_adhoc_context(self):
        webssl = manpki.tools.WebSSL()
        cert, pkey = webssl.generate_adhoc_ssl_context()
        self.assertTrue(os.path.isfile(cert))
        self.assertTrue(os.path.isfile(pkey))

    def test_manpki_tools_reloader_getargs(self):
        ret = manpki.tools.reloader._get_args_for_reloading()
        self.assertGreaterEqual(len(ret), 2)
        self.assertRegex(ret[0], "python")
        #self.assertEqual(ret[1], "tests/manpki_tests.py")

    def test_manpki_tools_reloader_itermodulefile(self):
        for i in manpki.tools.reloader._iter_module_files():
            self.assertEqual(type(i), str)
            self.assertTrue(os.path.isfile(i))

    @patch('signal.alarm', return_value=None)
    def test_manpki_tools_reloader_trigerreload(self, mock_reload):
        reloader = manpki.tools.reloader.ReloaderLoop()
        with self.assertRaises(SystemExit) as cm:
            reloader.trigger_reload('test/manpki_tests.py')
        self.assertEqual(cm.exception.code, 3)

    @patch('signal.alarm', return_value=None)
    def test_manpki_tools_reloader_trigerreloadwithsleep(self, mock_reload):
        reloader = manpki.tools.reloader.ReloaderLoop()
        with self.assertRaises(SystemExit) as cm:
            reloader.trigger_reload_with_sleep()
        self.assertEqual(cm.exception.code, 3)

    @patch('signal.alarm', return_value=None)
    def test_manpki_tools_reloader_statstrigerreloadwithsleep(self, mock_reload):
        with self.assertRaises(SystemExit) as cm:
            manpki.tools.reloader._reload()
        self.assertEqual(cm.exception.code, 3)

    def test_manpki_tools_event_new_event_on(self):
        manpki.tools.event.off_all()
        mock = MagicMock(return_value=None)
        manpki.tools.event.on('test.event', mock)
        manpki.tools.event.emit('test.event')
        self.assertTrue(mock.called)

    def test_manpki_tools_event_new_event_on_decorator(self):
        manpki.tools.event.off_all()
        mock = MagicMock(return_value=True)

        @manpki.tools.event.on('test.decorator')
        def event_func():
            mock()
            return True

        manpki.tools.event.emit('test.decorator')
        self.assertTrue(mock.called)

    def test_manpki_tools_event_new_event_on_any(self):
        manpki.tools.event.off_all()
        mock1 = MagicMock(return_value=True)
        mock2 = MagicMock(return_value=True)
        manpki.tools.event.on('test.not_event', mock1)
        manpki.tools.event.on_any(mock2)
        manpki.tools.event.emit('test.event')
        self.assertFalse(mock1.called)
        self.assertTrue(mock2.called)

    def test_manpki_tools_event_new_event_on_any_decorator(self):
        manpki.tools.event.off_all()
        mock1 = MagicMock(return_value=True)
        mock2 = MagicMock(return_value=True)

        @manpki.tools.event.on_any()
        def event_func():
            mock1()
            return True

        @manpki.tools.event.on('test.not_decorator')
        def event_func():
            mock2()
            return True

        manpki.tools.event.emit('test.decorator')
        self.assertTrue(mock1.called)
        self.assertFalse(mock2.called)

    def test_manpki_tools_event_new_event_off_any(self):
        manpki.tools.event.off_all()
        mock1 = MagicMock(return_value=True)

        @manpki.tools.event.on_any()
        def event_func():
            mock1()
            return True

        manpki.tools.event.off_any(event_func)
        manpki.tools.event.emit('test.decorator')
        self.assertFalse(mock1.called)

    def test_manpki_tools_event_listeners(self):
        manpki.tools.event.off_all()
        mock1 = MagicMock(return_value=True)
        manpki.tools.event.on('test.listeners', mock1)
        out = manpki.tools.event.listeners('test.listeners')
        self.assertEqual(len(out), 1)
        self.assertIsInstance(out[0], MagicMock)
        self.assertEqual(out[0], mock1)
        out = manpki.tools.event.listeners('test.not_listeners')
        self.assertEqual(len(out), 0)

    def test_manpki_tools_event_listeners_any(self):
        manpki.tools.event.off_all()
        mock1 = MagicMock(return_value=True)
        mock2 = MagicMock(return_value=True)
        manpki.tools.event.on('test.listeners', mock1)
        manpki.tools.event.on_any(mock2)
        out = manpki.tools.event.listeners_any()
        self.assertEqual(len(out), 1)
        self.assertIsInstance(out[0], MagicMock)
        self.assertEqual(out[0], mock2)

    def test_manpki_tools_event_listeners_all(self):
        manpki.tools.event.off_all()
        mock1 = MagicMock(return_value=True)
        mock2 = MagicMock(return_value=True)
        manpki.tools.event.on('test.listeners', mock1)
        manpki.tools.event.on_any(mock2)
        out = manpki.tools.event.listeners_all()
        self.assertEqual(len(out), 2)
        self.assertIsInstance(out[0], MagicMock)
        self.assertEqual(out[0], mock1)
        self.assertEqual(out[1], mock2)

    def test_manpki_version_init(self):
        ver = manpki._get_version_from_init()
        self.assertEqual(ver, manpki.VERSION)

    def test_manpki_version_from_file(self):
        if os.path.isfile(manpki._VERSION_FILE):
            os.unlink(manpki._VERSION_FILE)
        m = mock_open(read_data="1.1.1.1")
        with patch('manpki.open', m, create=True):
            ver = manpki._version()
        self.assertEqual(ver, "1.1.1.1")

    def test_manpki_version_from_file_ioerror(self):
        if os.path.isfile(manpki._VERSION_FILE):
            os.unlink(manpki._VERSION_FILE)
        mock = MagicMock()
        mock.mock_open.side_effect = IOError()
        with patch('manpki.open', mock.mock_open, create=True):
            ver = manpki._version()
        self.assertEqual(ver, manpki.VERSION)


if __name__ == '__main__':
    unittest.main()
