import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

logger = logging.getLogger('cyborgbackup')
logger.setLevel(logging.CRITICAL)


@patch('cyborgbackup.main.models.clients.Client.can_be_updated', return_value=False)
class CyborgbackupApiTest(APITestCase):
    fixtures = ["settings.json", "tests.json"]
    user_login = 'admin@cyborg.local'
    user_pass = 'adminadmin'

    def test_page_not_found(self, mocked):
        response = self.client.get('/notFound', format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_access_api(self, mocked):
        url = reverse('api:api_root_view')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['current_version'], '/api/v1/')

    def test_api_access_swagger(self, mocked):
        url = reverse('schema_json', kwargs={'format': '.json'})
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_api_access_login(self, mocked):
        url = reverse('api:login')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_api_access_logout(self, mocked):
        url = reverse('api:logout')
        response = self.client.post(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

    def test_api_v1_access_root(self, mocked):
        url = reverse('api:api_v1_root_view')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('/api/v1/ping', response.data['ping'])

    def test_api_v1_access_ping(self, mocked):
        url = reverse('api:api_v1_ping_view')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['version'], '1.4')
        self.assertEqual(response.data['ping'], 'pong')

    def test_api_v1_access_config_without_auth(self, mocked):
        url = reverse('api:api_v1_config_view')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_v1_access_config_with_auth(self, mocked):
        url = reverse('api:api_v1_config_view')
        user = get_user_model().objects.first()
        self.client.force_login(user)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['time_zone'], 'UTC')
        self.assertFalse(response.data['debug'])
        self.assertFalse(response.data['sql_debug'])
        self.assertEqual(response.data['version'], '1.4')

    def test_api_v1_access_me(self, mocked):
        url = reverse('api:user_me_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['type'], 'user')
        self.assertTrue(response.data['results'][0]['is_superuser'])
        self.assertEqual(response.data['results'][0]['email'], 'admin@cyborg.local')

    def test_api_v1_access_users(self, mocked):
        url = reverse('api:user_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_api_v1_access_settings(self, mocked):
        url = reverse('api:setting_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 22)

    def test_api_v1_access_clients(self, mocked):
        url = reverse('api:client_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_api_v1_access_schedules(self, mocked):
        url = reverse('api:schedule_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_api_v1_access_repositories(self, mocked):
        url = reverse('api:repository_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_api_v1_access_policies(self, mocked):
        url = reverse('api:policy_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_api_v1_access_catalogs(self, mocked):
        url = reverse('api:catalog_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_api_v1_access_stats(self, mocked):
        url = reverse('api:stats')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_api_v1_get_schedule_1(self, mocked):
        url = reverse('api:schedule_detail', kwargs={'pk': 1})
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], 1)
        self.assertEqual(response.data['crontab'], "0 5 * * MON *")
        self.assertFalse(response.data['enabled'])

    def test_api_v1_access_schedules_create_schedule(self, mocked):
        url = reverse('api:schedule_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test Create Schedule", "crontab": "1 1 1 1 * *"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['crontab'], "1 1 1 1 * *")
        self.assertEqual(response.data['name'], "Test Create Schedule")
        self.assertTrue(response.data['enabled'])

    def test_api_v1_access_schedules_after_creation(self, mocked):
        url = reverse('api:schedule_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test List Schedule", "crontab": "1 1 1 1 * *"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('api:schedule_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['count'], 0)

    def test_api_v1_access_schedules_update_schedule(self, mocked):
        url = reverse('api:schedule_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test Update Schedule", "crontab": "2 2 2 2 * *"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        id = response.data['id']

        url = reverse('api:schedule_detail', kwargs={'pk': response.data['id']})
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"enabled": False}
        response = self.client.patch(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], id)
        self.assertEqual(response.data['crontab'], "2 2 2 2 * *")
        self.assertEqual(response.data['name'], "Test Update Schedule")
        self.assertIn(url, response.data['url'])
        self.assertFalse(response.data['enabled'])

    def test_api_v1_access_schedules_delete_schedule(self, mocked):
        url = reverse('api:schedule_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_before_delete = response.data['count']

        url = reverse('api:schedule_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test Delete Schedule", "crontab": "1 1 1 1 * *"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('api:schedule_detail', kwargs={ 'pk': response.data['id']})
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.delete(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        url = reverse('api:schedule_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_after_delete = response.data['count']

        self.assertEqual(count_before_delete, count_after_delete)

    def test_api_v1_get_repository_1(self, mocked):
        url = reverse('api:repository_detail', kwargs={'pk': 1})
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], 1)
        self.assertEqual(response.data['name'], "Demo Repository")
        self.assertFalse(response.data['enabled'])
        self.assertEqual(response.data['path'], "/tmp/repository")
        self.assertEqual(response.data['repository_key'], "0123456789abcdef")

    def test_api_v1_access_repositories_create_repository(self, mocked):
        url = reverse('api:repository_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test Create Repository", "path": "/dev/null", "repository_key": "abcedf02"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], "Test Create Repository")
        self.assertEqual(response.data['path'], "/dev/null")
        self.assertTrue(response.data['enabled'])

    def test_api_v1_access_repositories_after_creation(self, mocked):
        url = reverse('api:repository_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test List Repository", "path": "/dev/log", "repository_key": "abcedf03"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('api:repository_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['count'], 0)

    def test_api_v1_access_repositories_update_repository(self, mocked):
        url = reverse('api:repository_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test Update Repository", "path": "/dev/log", "repository_key": "abcedf04"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        id = response.data['id']

        url = reverse('api:repository_detail', kwargs={'pk': response.data['id']})
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"enabled": False, "path": "/dev/null"}
        response = self.client.patch(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], id)
        self.assertEqual(response.data['path'], "/dev/null")
        self.assertEqual(response.data['name'], "Test Update Repository")
        self.assertIn(url, response.data['url'])
        self.assertFalse(response.data['enabled'])

    def test_api_v1_access_repositories_delete_repository(self, mocked):
        url = reverse('api:repository_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_before_delete = response.data['count']

        url = reverse('api:repository_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test Delete Repository", "path": "/dev/none", "repository_key": "abcedf05"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('api:repository_detail', kwargs={'pk': response.data['id']})
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.delete(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        url = reverse('api:repository_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_after_delete = response.data['count']

        self.assertEqual(count_before_delete, count_after_delete)

    def test_api_v1_get_client_1(self, mocked):
        url = reverse('api:client_detail', kwargs={'pk': 1})
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], 1)
        self.assertEqual(response.data['hostname'], "localhost")
        self.assertFalse(response.data['enabled'])
        self.assertEqual(response.data['ip'], "")
        self.assertFalse(response.data['ready'])

    def test_api_v1_access_clients_create_client(self, mocked):
        url = reverse('api:client_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"hostname": "localhost.localdomain"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['hostname'], "localhost.localdomain")
        self.assertTrue(response.data['enabled'])

    def test_api_v1_access_clients_after_creation(self, mocked):
        url = reverse('api:client_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"hostname": "localhost.contoso"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('api:client_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['count'], 0)

    def test_api_v1_access_clients_update_client(self, mocked):
        url = reverse('api:client_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"hostname": "localhost.example"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        id = response.data['id']

        url = reverse('api:client_detail', kwargs={'pk': response.data['id']})
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"enabled": False}
        response = self.client.patch(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], id)
        self.assertEqual(response.data['hostname'], "localhost.example")
        self.assertIn(url, response.data['url'])
        self.assertFalse(response.data['enabled'])

    def test_api_v1_access_clients_delete_client(self, mocked):
        url = reverse('api:client_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_before_delete = response.data['count']

        url = reverse('api:client_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"hostname": "localhost.test"}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('api:client_detail', kwargs={'pk': response.data['id']})
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.delete(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        url = reverse('api:client_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_after_delete = response.data['count']

        self.assertEqual(count_before_delete, count_after_delete)

    def test_api_v1_get_policy_1(self, mocked):
        url = reverse('api:policy_detail', kwargs={'pk': 1})
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], 1)
        self.assertEqual(response.data['name'], "Demo Policy")
        self.assertFalse(response.data['enabled'])
        self.assertEqual(response.data['policy_type'], "rootfs")

    def test_api_v1_get_policy_vmmmodule(self, mocked):
        url = reverse('api:policy_vmmodule')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_api_v1_get_policy_calendar_1(self, mocked):
        url = reverse('api:policy_calendar', kwargs={'pk': 1})
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')

        import datetime
        import tzcron
        import dateutil
        import pytz

        now = datetime.datetime.now(pytz.utc)
        start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year = now.year
        if start_month.month == 12:
            year += 1
        relative_month = dateutil.relativedelta.relativedelta(months=1)
        end_month = datetime.datetime(year, (start_month + relative_month).month, 1) - datetime.timedelta(days=1)
        end_month = end_month.replace(hour=23, minute=59, second=50, tzinfo=pytz.utc)
        schedule = tzcron.Schedule("0 5 * * MON *", pytz.utc, start_month, end_month)

        expectedCalendar = [s.isoformat() for s in schedule]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, expectedCalendar)

    def test_api_v1_access_policies_create_policy(self, mocked):
        url = reverse('api:policy_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test Create Policy", "policy_type": "config", "schedule": 1, "repository": 1, "clients": [1]}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], "Test Create Policy")
        self.assertEqual(response.data['policy_type'], "config")
        self.assertTrue(response.data['enabled'])

    def test_api_v1_access_policies_after_policy(self, mocked):
        url = reverse('api:policy_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test List Policy", "policy_type": "config", "schedule": 1, "repository": 1, "clients": [1]}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('api:policy_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data['count'], 0)

    def test_api_v1_access_policies_update_policy(self, mocked):
        url = reverse('api:policy_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test Update Policy", "policy_type": "config", "schedule": 1, "repository": 1, "clients": [1]}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        id = response.data['id']

        url = reverse('api:policy_detail', kwargs={'pk': response.data['id']})
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"enabled": False}
        response = self.client.patch(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], id)
        self.assertEqual(response.data['name'], "Test Update Policy")
        self.assertIn(url, response.data['url'])
        self.assertFalse(response.data['enabled'])

    def test_api_v1_access_policies_delete_policy(self, mocked):
        url = reverse('api:policy_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_before_delete = response.data['count']

        url = reverse('api:policy_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        data = {"name": "Test Delete Policy", "policy_type": "config", "schedule": 1, "repository": 1, "clients": [1]}
        response = self.client.post(url, data=data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = reverse('api:policy_detail', kwargs={'pk': response.data['id']})
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.delete(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        url = reverse('api:policy_list')
        self.client.login(username=self.user_login, password=self.user_pass)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count_after_delete = response.data['count']

        self.assertEqual(count_before_delete, count_after_delete)
